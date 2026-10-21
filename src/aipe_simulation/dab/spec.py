"""Typed DAB circuit specification with SI units and a canonical hash.

All quantities are SI base units (V, A, Hz, H, F, Ohm, s) except ``phi_deg``,
which is kept in degrees because engineers specify phase shift that way; the
radian value is derived. Defaults reproduce the ideal Level 1 benchmark of the
AIPE 10 kW DAB task (800 V / 400 V, 100 kHz, n = 2, L = 35 uH, phi = 22.5 deg).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Optional


def _coerce_numbers(data: dict[str, Any]) -> dict[str, Any]:
    """Convert numeric strings (e.g. YAML 1.1 '1.0e7', which PyYAML reads as text) to floats, recursively."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[key] = _coerce_numbers(value)
        elif isinstance(value, str):
            try:
                out[key] = float(value) if any(ch in value for ch in ".eE") or value.lstrip("-+").isdigit() else value
            except ValueError:
                out[key] = value
        else:
            out[key] = value
    return out


@dataclass
class PortModel:
    """DC port representation.

    ``voltage_source``: ideal stiff DC source (bidirectional port, used for the
    analytical benchmark). ``rc_load``: DC-link capacitor (with optional ESR/ESL)
    and resistive load; the voltage then floats and is an output of the run.
    """

    type: str = "voltage_source"  # voltage_source | rc_load
    capacitance: float = 0.0  # F
    esr: float = 0.0  # Ohm
    esl: float = 0.0  # H
    # Resistance in parallel with the ESL representing high-frequency loss of the loop; 0 = automatic
    # sqrt(ESL / C_oss) (near-critical damping of the ESL-Coss resonance), which keeps the behavioural
    # model solvable. Layout-specific damping must come from measurements or field simulation.
    esl_damping_resistance: float = 0.0  # Ohm
    local_decoupling_capacitance: float = 0.0  # F; low-inductance ceramics at the bridge (0 disables)
    local_decoupling_esr: float = 2e-3  # Ohm
    local_decoupling_esl: float = 0.5e-9  # H
    load_resistance: float = 0.0  # Ohm (rc_load only)
    initial_voltage: Optional[float] = None  # V (rc_load only)


@dataclass
class DcLinkModel:
    """Optional DC-link capacitor and source impedance for Level 2."""

    capacitance: float = 0.0  # F; 0 disables
    esr: float = 0.0  # Ohm
    esl: float = 0.0  # H
    esl_damping_resistance: float = 0.0  # Ohm in parallel with the ESL (0 = automatic sqrt(ESL/C_oss))
    # Local low-inductance (ceramic) decoupling right at the bridge, as in real designs (e.g. 14 x 0.47 uF
    # 2220 ceramics in TIDA-010054). Without it, nanosecond commutation edges through the bulk capacitor's
    # ESL produce hundreds of volts of L di/dt overshoot on the link node and the solver may fail.
    local_decoupling_capacitance: float = 0.0  # F; 0 disables
    local_decoupling_esr: float = 2e-3  # Ohm
    local_decoupling_esl: float = 0.5e-9  # H (paralleled ceramics)
    source_resistance: float = 0.0  # Ohm between the DC source and the link
    source_inductance: float = 0.0  # H
    source_damping_resistance: float = 0.0  # Ohm in parallel with the source inductance (0 = automatic)


@dataclass
class SwitchModel:
    """Switch representation for the ideal/behavioural levels.

    ``r_on`` is the on-state resistance of the controlled switch; the
    antiparallel diode is a SPICE ``D`` model with saturation current ``d_is``,
    ideality ``d_n`` and series resistance ``d_rs``. ``c_oss`` is a linear
    output capacitance placed across each switch (0 disables). Level 3 replaces
    this block with qualified manufacturer models and is not part of this spec.
    """

    # Channel model: "sw" = ngspice voltage-controlled switch (fast, ideal; Level 1), "behavioural" = B-source
    # conductance g = Gon * smoothstep((v_gs - Vt + w) / 2w) + Goff with a C1-continuous clamped cubic step
    # (exactly off below Vt - w, exactly on above Vt + w) so that Newton converges when Coss branches hang
    # on the switching node (Level 2).
    # "auto" selects sw for Level 1 and behavioural for Level 2.
    model: str = "auto"
    transition_voltage: float = 1.5  # V; half-width w of the behavioural channel transition (Vt +/- w)
    r_on: float = 1e-3  # Ohm
    r_off: float = 1e7  # Ohm
    c_oss: float = 0.0  # F (linear approximation)
    # Series damping of the linear Coss (represents the finite di/dt of the channel during turn-on);
    # without it a capacitor across a milliohm channel has an unresolvable picosecond time constant.
    c_oss_esr: float = 1.0  # Ohm
    d_is: float = 1e-12  # A
    d_n: float = 1.0
    d_rs: float = 1e-3  # Ohm
    d_cjo: float = 0.0  # F (a capacitance directly across a milliohm switch creates an unresolvable time constant)
    # Optional damped RC snubber across every switch pair purely as a numerical aid: it defines the
    # mid-node voltage when neither switch nor diode conducts. Dissipation ~ C V^2 f_sw per switch
    # is itemised in the energy balance. 0 disables.
    snubber_c: float = 0.0  # F
    snubber_r: float = 100.0  # Ohm
    gate_voltage: float = 15.0  # V (logic level of the ideal gate signals)
    # 10 ns edges with a 3 V switch transition band give a 2 ns resistive transition that the
    # solver can resolve; edge mid-points are placed on the ideal switching instants.
    gate_rise_fall: float = 10e-9  # s


@dataclass
class SimulationSettings:
    """Solver settings; all recorded in the run metadata."""

    cycles: int = 24  # simulated switching periods
    output_from_cycle: int = 0  # suppress raw output before this cycle (saves memory)
    max_step_fraction: int = 400  # tmax = T / max_step_fraction
    method: str = "gear"  # gear | trap
    maxord: int = 2
    reltol: float = 1e-4
    abstol: float = 1e-9  # A
    vntol: float = 1e-6  # V
    chgtol: float = 1e-14  # C
    # The transient always skips the DC operating point (uic). ``initial_series_current`` sets
    # i_L(0) at the centre of the primary positive half-cycle (e.g. the analytic steady-state
    # value) so that the periodic state is reached immediately; ``None`` starts from zero.
    use_initial_conditions: bool = False  # informational flag recorded with the run
    initial_series_current: Optional[float] = None  # A
    # Magnetising current at t = 0. Its zero crossing lies at the centre of the transformer
    # voltage half-cycle (shifted by t_phi from the primary centre), so the periodic value is
    # -V2' t_phi / L_m. ``None`` uses that periodic value whenever initial_series_current is set,
    # otherwise 0 (a start-up DC offset then decays with L_m / R, which can take many cycles).
    initial_magnetising_current: Optional[float] = None  # A
    timeout_s: float = 1800.0


@dataclass
class DabCircuitSpec:
    """Complete description of one DAB switching-circuit experiment."""

    name: str = "dab-10kw-level1-nominal"
    level: int = 1  # 1 ideal switching model, 2 non-ideal behavioural model
    v1: float = 800.0  # V, port 1 DC voltage
    v2: float = 400.0  # V, port 2 DC voltage (voltage_source port) or initial/expected (rc_load)
    f_sw: float = 100e3  # Hz
    phi_deg: float = 22.5  # degrees; positive = secondary lags, power 1 -> 2
    n_ratio: float = 2.0  # N_p / N_s
    l_ext: float = 35e-6  # H, external series inductance, primary side
    l_lk_p: float = 0.0  # H, transformer leakage, primary winding
    l_lk_s: float = 0.0  # H, transformer leakage, secondary winding (secondary side value)
    l_m: float = 1e-3  # H, magnetising inductance referred to the primary
    r_series_p: float = 20e-3  # Ohm, primary-side series resistance (inductor + winding; also damps start-up DC offset)
    r_series_s: float = 0.0  # Ohm, secondary winding resistance
    dead_time: float = 0.0  # s, per leg commutation dead time
    switch: SwitchModel = field(default_factory=SwitchModel)
    port1: PortModel = field(default_factory=PortModel)
    port2: PortModel = field(default_factory=PortModel)
    dc_link1: DcLinkModel = field(default_factory=DcLinkModel)
    dc_link2: DcLinkModel = field(default_factory=DcLinkModel)
    sim: SimulationSettings = field(default_factory=SimulationSettings)
    notes: list[str] = field(default_factory=list)

    # ---- derived quantities -------------------------------------------------
    @property
    def period(self) -> float:
        return 1.0 / self.f_sw

    @property
    def phi_rad(self) -> float:
        return math.radians(self.phi_deg)

    @property
    def t_phi(self) -> float:
        """Time shift of the secondary bridge relative to the primary (signed)."""
        return self.phi_rad / (2 * math.pi) * self.period

    @property
    def l_total_primary(self) -> float:
        """Total series inductance referred to the primary (external + leakages)."""
        return self.l_ext + self.l_lk_p + self.l_lk_s * self.n_ratio ** 2

    @property
    def v2_referred(self) -> float:
        return self.n_ratio * self.v2

    @property
    def switch_model(self) -> str:
        """Resolved channel model: sw for Level 1, behavioural for Level 2 unless forced."""
        if self.switch.model == "auto":
            return "sw" if self.level == 1 else "behavioural"
        return self.switch.model

    @property
    def periodic_magnetising_current_at_origin(self) -> float:
        """Periodic steady-state magnetising current at t = 0 (centre of primary positive half-cycle)."""
        return -self.v2_referred * self.t_phi / self.l_m

    @property
    def t_max(self) -> float:
        return self.period / self.sim.max_step_fraction

    @property
    def t_stop(self) -> float:
        return self.sim.cycles * self.period

    @property
    def t_output_start(self) -> float:
        return self.sim.output_from_cycle * self.period

    # ---- serialisation ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DabCircuitSpec":
        data = _coerce_numbers(dict(data))
        for key, sub in (("switch", SwitchModel), ("port1", PortModel), ("port2", PortModel),
                         ("dc_link1", DcLinkModel), ("dc_link2", DcLinkModel), ("sim", SimulationSettings)):
            if key in data and isinstance(data[key], dict):
                allowed = {f.name for f in fields(sub)}
                unknown = set(data[key]) - allowed
                if unknown:
                    raise ValueError(f"unknown {key} fields: {sorted(unknown)}")
                data[key] = sub(**data[key])
        allowed = {f.name for f in fields(cls)}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown DabCircuitSpec fields: {sorted(unknown)}")
        return cls(**data)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    def sha256(self) -> str:
        """Hash of the complete specification (the 'input design-state hash')."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    # ---- validation ---------------------------------------------------------
    def validate(self) -> list[str]:
        problems = []
        if self.level not in (1, 2):
            problems.append("level must be 1 or 2 (level 3 uses qualified manufacturer models and a separate generator)")
        for name in ("v1", "v2", "f_sw", "n_ratio", "l_m"):
            if getattr(self, name) <= 0:
                problems.append(f"{name} must be positive")
        if self.l_total_primary <= 0:
            problems.append("total series inductance must be positive")
        if not -90.0 <= self.phi_deg <= 90.0:
            problems.append("phi_deg must lie within [-90, 90] for SPS power transfer")
        if self.dead_time < 0 or self.dead_time >= self.period / 4:
            problems.append("dead_time must be non-negative and smaller than a quarter period")
        if self.sim.cycles < 2:
            problems.append("sim.cycles must be at least 2")
        if self.sim.max_step_fraction < 50:
            problems.append("sim.max_step_fraction below 50 cannot resolve switching edges")
        if self.sim.method not in ("gear", "trap"):
            problems.append("sim.method must be gear or trap")
        for port_name in ("port1", "port2"):
            port = getattr(self, port_name)
            if port.type not in ("voltage_source", "rc_load"):
                problems.append(f"{port_name}.type must be voltage_source or rc_load")
            if port.type == "rc_load" and (port.capacitance <= 0 or port.load_resistance <= 0):
                problems.append(f"{port_name} rc_load needs positive capacitance and load_resistance")
        if self.port1.type == "rc_load":
            problems.append("port1 must be a voltage_source in this generator (source side)")
        if self.level == 1 and (self.dead_time > 0 or self.switch.c_oss > 0):
            problems.append("level 1 is the ideal reference: dead_time and c_oss must be zero (use level 2)")
        if self.switch.model not in ("auto", "sw", "behavioural"):
            problems.append("switch.model must be auto, sw or behavioural")
        if self.switch.transition_voltage <= 0 or self.switch.transition_voltage >= self.switch.gate_voltage / 2:
            problems.append("switch.transition_voltage must be positive and below half the gate voltage")
        if self.switch.c_oss > 0 and self.switch.c_oss_esr * self.switch.c_oss < 1e-11:
            problems.append("c_oss_esr * c_oss must be at least 10 ps for the solver to resolve the Coss transition")
        if self.switch.snubber_c > 0 and self.switch.snubber_r * self.switch.snubber_c < 1e-10:
            problems.append("numerical snubber time constant R*C must be at least 0.1 ns to be resolvable")
        return problems
