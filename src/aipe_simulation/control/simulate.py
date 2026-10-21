"""Closed-loop host simulation of DAB output-voltage regulation with current limiting.

Control structure (one ISR per switching period, ``Ts = 1 / f_sw``)::

    v_ref --(rate limit)--> [2P2Z voltage loop] --> i_ref, clamped to +-I_lim
          --> [PI current loop on the port-2 DC current] --> phi_cmd
          --(computation delay z^-1: shadow-register load at the next period boundary)-->
          [SPS modulator: command limit, slew limit, timer quantisation] --> phi_applied
          --> [cycle-averaged plant: lossless SPS law, C2 with load]

Measurements available at sample ``k``: ``v2[k]`` (port-2 voltage at the period
boundary) and ``i2`` averaged over the previous period (one-period averaging
delay, as a sinc filter or oversampling would provide). The quasi-static
lossless series-current peak of the previous period is used by the
over-current protection.

Supervisory state machine::

    IDLE/OFF --start (precharge interlock)--> SOFT_START --handover--> RUN --shutdown--> SHUTDOWN --> OFF
    any active state --trip--> FAULT (gates off, latched until an explicit reset while no condition persists)

Soft start is an open-loop phase-shift ramp; the hand-over to closed loop is
bumpless (controller states are initialised to the applied phase shift and the
measured current). Everything is a host-side model: no firmware was built or run.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from .. import __version__ as PACKAGE_VERSION
from ..waveforms.dataset import WaveformDataset
from .controllers import Df22Compensator, DiscretePI, LoopSummary, design_2p2z, design_pi_for_static_plant, stability_margins
from .plant import MODEL_ASSUMPTIONS, DabSpsPlant, DabSpsPlantParameters, output_current_gain, phase_shift_for_output_current
from .sps_modulator import SpsModulator, SpsModulatorConfig
from .ztf import ZTransfer

MODES = ("IDLE", "SOFT_START", "RUN", "SHUTDOWN", "OFF", "FAULT")
ACTIVE_MODES = {"SOFT_START", "RUN", "SHUTDOWN"}
SCHEMA = "aipe-dab-sps-control-sim/0.1"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------------ design

@dataclass
class ProtectionLimits:
    """Protection thresholds (AIPE assumptions for the 10 kW benchmark; see the control spec)."""

    i_l_peak_trip_A: float = 40.0  # quasi-static lossless series-current peak, primary referred
    v2_over_V: float = 460.0
    v2_under_V: float = 300.0  # armed in RUN only
    soft_start_timeout_s: float = 0.05


@dataclass
class ControlDesign:
    """Complete parameter set of the SPS control baseline (SI units unless suffixed)."""

    plant: DabSpsPlantParameters = field(default_factory=DabSpsPlantParameters)
    v_ref: float = 400.0  # V
    nominal_power_W: float = 10000.0
    computation_delay_samples: int = 1  # 1 = shadow-register load at the next period boundary; 0 = idealised immediate update
    measurement_delay_samples: int = 1  # one-period averaging of the measured port-2 current
    f_c_current_Hz: float = 2000.0
    pi_high_frequency_gain: float = 0.25
    f_c_voltage_Hz: float = 300.0
    pm_voltage_deg: float = 60.0
    f_pole_voltage_Hz: float = 5000.0
    i_ref_limit_A: float = 30.0  # output-current reference clamp (both directions)
    phi_max_deg: float = 45.0
    phi_slew_deg_per_update: float = 1.0  # modulator rate limit; 1 deg/period = 100 deg/ms
    pwm_clock_Hz: float = 100e6
    hr_step_s: Optional[float] = 150e-12
    dead_time_s: float = 200e-9
    quantise: bool = True
    soft_start_rate_deg_per_ms: float = 2.0
    soft_start_phi_max_deg: float = 30.0
    handover_fraction: float = 0.99
    precharge_min_fraction: float = 0.8
    v_ref_slew_V_per_s: float = 20e3
    protection: ProtectionLimits = field(default_factory=ProtectionLimits)

    @property
    def ts(self) -> float:
        return self.plant.ts

    def modulator_config(self) -> SpsModulatorConfig:
        return SpsModulatorConfig(f_sw=self.plant.f_sw, pwm_clock_hz=self.pwm_clock_Hz, hr_step_s=self.hr_step_s,
                                  dead_time=self.dead_time_s, phi_max_rad=math.radians(self.phi_max_deg),
                                  slew_max_rad_per_update=math.radians(self.phi_slew_deg_per_update), quantise=self.quantise)

    def validate(self) -> list[str]:
        problems = self.plant.validate()
        problems += self.modulator_config().validate()
        if self.v_ref <= 0 or self.nominal_power_W <= 0:
            problems.append("v_ref and nominal_power_W must be positive")
        if self.computation_delay_samples not in (0, 1):
            problems.append("computation_delay_samples must be 0 or 1")
        if self.measurement_delay_samples < 0:
            problems.append("measurement_delay_samples must be non-negative")
        if not 0 < self.f_c_voltage_Hz < self.f_c_current_Hz < 0.5 * self.plant.f_sw:
            problems.append("need 0 < f_c_voltage < f_c_current < f_sw / 2 (cascaded loops with separated bandwidths)")
        if self.i_ref_limit_A <= 0 or self.i_ref_limit_A > self.plant.i2_max:
            problems.append("i_ref_limit_A must be positive and below the SPS maximum current")
        if not 0 < self.soft_start_phi_max_deg <= self.phi_max_deg:
            problems.append("soft_start_phi_max_deg must lie in (0, phi_max_deg]")
        if not 0 < self.handover_fraction <= 1 or not 0 <= self.precharge_min_fraction < 1:
            problems.append("handover_fraction in (0, 1] and precharge_min_fraction in [0, 1) required")
        if self.protection.v2_under_V >= self.v_ref or self.protection.v2_over_V <= self.v_ref:
            problems.append("protection thresholds must bracket v_ref")
        return problems

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ControlDesign":
        data = dict(data)
        for key, sub in (("plant", DabSpsPlantParameters), ("protection", ProtectionLimits)):
            if key in data and isinstance(data[key], dict):
                allowed = {f.name for f in fields(sub)}
                unknown = set(data[key]) - allowed
                if unknown:
                    raise ValueError(f"unknown {key} fields: {sorted(unknown)}")
                data[key] = sub(**data[key])
        allowed = {f.name for f in fields(cls)}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown ControlDesign fields: {sorted(unknown)}")
        return cls(**data)

    def sha256(self) -> str:
        text = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ControllerSet:
    """Designed controller parameters plus the JSON report of the design."""

    pi_kp: float
    pi_ki: float
    df22: dict
    ts: float
    i_ref_limit: float
    phi_max_rad: float
    report: dict

    def new_pi(self) -> DiscretePI:
        return DiscretePI(self.pi_kp, self.pi_ki, self.ts, -self.phi_max_rad, self.phi_max_rad)

    def new_df22(self) -> Df22Compensator:
        c = self.df22
        return Df22Compensator(c["b0"], c["b1"], c["b2"], c["a1"], c["a2"], -self.i_ref_limit, self.i_ref_limit)


def _strip(margins: dict) -> dict:
    return {k: v for k, v in margins.items() if k not in ("all_gain_crossovers", "all_phase_crossovers")}


def design_controllers(design: ControlDesign) -> ControllerSet:
    """Design both loops at the nominal operating point and report margins at the corners."""
    problems = design.validate()
    if problems:
        raise ValueError("invalid control design: " + "; ".join(problems))
    p = design.plant
    ts = design.ts
    plant = DabSpsPlant(replace(p), design.v_ref)
    i2_nom = design.nominal_power_W / design.v_ref
    phi_nom = phase_shift_for_output_current(p.v1, p.n_ratio, p.f_sw, p.l_total, i2_nom)
    k_nom = output_current_gain(p.v1, p.n_ratio, p.f_sw, p.l_total, phi_nom)
    k_max = output_current_gain(p.v1, p.n_ratio, p.f_sw, p.l_total, 0.0)
    k_min = output_current_gain(p.v1, p.n_ratio, p.f_sw, p.l_total, math.radians(design.phi_max_deg))
    d_comp, d_meas = design.computation_delay_samples, design.measurement_delay_samples
    pi_design = design_pi_for_static_plant(k_nom, design.f_c_current_Hz, ts, delay_samples=d_comp + d_meas,
                                           high_frequency_gain=design.pi_high_frequency_gain,
                                           u_min=-math.radians(design.phi_max_deg), u_max=math.radians(design.phi_max_deg))
    pi_tf = pi_design["pi"].transfer_function()

    def inner_closed(k: float) -> ZTransfer:
        # i2 = K z^-d_comp phi_cmd ; i_meas = z^-d_meas i2 ; phi_cmd = C_pi (i_ref - i_meas)
        return (pi_tf * ZTransfer.gain(k).delayed(d_comp)).feedback(ZTransfer.delay(d_meas))

    def inner_open(k: float) -> ZTransfer:
        return pi_tf * ZTransfer.gain(k).delayed(d_comp + d_meas)

    z_full = plant.output_port_tf()
    z_no_load = plant.output_port_tf(None)
    rest_full = inner_closed(k_nom) * z_full
    v_design = design_2p2z(rest_full, ts, design.f_c_voltage_Hz, design.pm_voltage_deg, design.f_pole_voltage_Hz,
                           y_min=-design.i_ref_limit_A, y_max=design.i_ref_limit_A)
    c_v = v_design["compensator"].transfer_function()
    summaries = {
        "current_loop_nominal": LoopSummary("current loop, nominal operating point", design.f_c_current_Hz, pi_design["margins"],
                                            [f"plant gain dI2/dphi = {k_nom:.4g} A/rad at phi = {math.degrees(phi_nom):.3g} deg",
                                             f"{d_comp} computation + {d_meas} measurement sample(s) of delay"]),
        "current_loop_max_gain": LoopSummary("current loop at phi -> 0 (maximum plant gain)", design.f_c_current_Hz,
                                             stability_margins(inner_open(k_max), ts), [f"plant gain {k_max:.4g} A/rad"]),
        "current_loop_min_gain": LoopSummary("current loop at phi = phi_max (minimum plant gain)", design.f_c_current_Hz,
                                             stability_margins(inner_open(k_min), ts), [f"plant gain {k_min:.4g} A/rad"]),
        "voltage_loop_full_load": LoopSummary("voltage loop, nominal load", design.f_c_voltage_Hz, v_design["margins"],
                                              [f"R_load = {p.r_load} Ohm, C2 = {p.c2} F, inner loop at nominal gain"]),
        "voltage_loop_no_load": LoopSummary("voltage loop, no resistive load (pure capacitor)", design.f_c_voltage_Hz,
                                            stability_margins(c_v * inner_closed(k_nom) * z_no_load, ts), ["Z(z) = Ts/(C2 (z - 1))"]),
        "voltage_loop_max_inner_gain": LoopSummary("voltage loop, nominal load, inner loop at maximum plant gain", design.f_c_voltage_Hz,
                                                   stability_margins(c_v * inner_closed(k_max) * z_full, ts), []),
    }
    report = {
        "operating_point": {"v1_V": p.v1, "v2_V": design.v_ref, "p_W": design.nominal_power_W, "i2_A": i2_nom,
                            "phi_rad": phi_nom, "phi_deg": math.degrees(phi_nom), "dI2_dphi_A_per_rad": k_nom,
                            "dI2_dphi_range_A_per_rad": [k_min, k_max], "dP_dphi_W_per_rad": design.v_ref * k_nom},
        "sampling": {"ts_s": ts, "f_s_Hz": 1.0 / ts, "computation_delay_samples": d_comp, "measurement_delay_samples": d_meas,
                     "note": "one ISR per switching period; both loops at f_s"},
        "current_loop": {"structure": "PI on the cycle-averaged port-2 DC current; plant = static gain dI2/dphi with delays",
                         "kp_rad_per_A": pi_design["kp"], "ki_rad_per_A_s": pi_design["ki"], "ki_per_sample_rad_per_A": pi_design["ki_per_sample"],
                         "output_limit_rad": math.radians(design.phi_max_deg), "high_frequency_loop_gain": design.pi_high_frequency_gain,
                         "f_c_target_Hz": design.f_c_current_Hz, "pi": pi_design["pi"].to_dict()},
        "voltage_loop": {"structure": "2P2Z (DF22) on the port-2 voltage error, output = current reference clamped to +-i_ref_limit",
                         "coefficients": v_design["coefficients"], "difference_equation": "y[n] = b0 e[n] + b1 e[n-1] + b2 e[n-2] - a1 y[n-1] - a2 y[n-2]",
                         "continuous_prototype": v_design["prototype"], "phase_of_rest_of_loop_at_fc_deg": v_design["phase_rest_at_fc_deg"],
                         "pm_target_deg": design.pm_voltage_deg, "f_c_target_Hz": design.f_c_voltage_Hz,
                         "output_limit_A": design.i_ref_limit_A, "plant_pole_full_load_Hz": plant.small_signal(phi_nom)["output_port_pole_Hz"],
                         "df22": v_design["compensator"].to_dict()},
        "loops": {name: s.to_dict() for name, s in summaries.items()},
        "margins_detail": {"current_loop_nominal": _strip(pi_design["margins"]), "voltage_loop_full_load": _strip(v_design["margins"])},
    }
    return ControllerSet(pi_design["kp"], pi_design["ki"], v_design["coefficients"], ts, design.i_ref_limit_A,
                         math.radians(design.phi_max_deg), report)


# ---------------------------------------------------------------------- scenarios

@dataclass
class Event:
    t: float  # s
    kind: str  # start | load_resistance | load_current | setpoint | shutdown | fault_reset | source_voltage
    value: Any = None
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Scenario:
    name: str
    t_end: float
    v2_initial: float
    r_load_initial: Optional[float]
    i_load_initial: float
    events: list[Event]
    description: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "t_end_s": self.t_end, "v2_initial_V": self.v2_initial, "r_load_initial_Ohm": self.r_load_initial,
                "i_load_initial_A": self.i_load_initial, "description": self.description, "events": [e.to_dict() for e in self.events]}


def nominal_scenario(design: ControlDesign) -> Scenario:
    r_full = design.v_ref ** 2 / design.nominal_power_W  # 16 Ohm at 400 V / 10 kW
    return Scenario(
        name="nominal", t_end=0.140, v2_initial=0.875 * design.v_ref, r_load_initial=4 * r_full, i_load_initial=0.0,
        description="precharged start at 25 % load, full-load step, set-point change, load release, power reversal, "
                    "return to forward full load, overload into the current limit, recovery and controlled shutdown",
        events=[
            Event(0.0, "start", label="startup"),
            Event(0.020, "load_resistance", r_full, "load step 25 % -> 100 %"),
            Event(0.040, "setpoint", 0.95 * design.v_ref, "set-point 400 V -> 380 V"),
            Event(0.055, "load_resistance", None, "load release 100 % -> 0"),
            Event(0.065, "load_current", -0.5 * design.nominal_power_W / design.v_ref, "power reversal: 12.5 A injected (5 kW regenerative)"),
            Event(0.075, "load_current", 0.0),  # same instant as the next event; unlabelled so that only one window is formed
            Event(0.075 + 1e-9, "load_resistance", r_full, "forward full load"),
            Event(0.085, "setpoint", design.v_ref, "set-point 380 V -> 400 V"),
            Event(0.095, "load_resistance", 0.75 * r_full, "overload 133 % (current limit)"),
            Event(0.110, "load_resistance", r_full, "overload removed"),
            Event(0.120, "shutdown", label="shutdown"),
        ])


def fault_scenario(design: ControlDesign) -> Scenario:
    r_full = design.v_ref ** 2 / design.nominal_power_W
    return Scenario(
        name="fault", t_end=0.040, v2_initial=0.875 * design.v_ref, r_load_initial=4 * r_full, i_load_initial=0.0,
        description="precharged start at 25 % load, full load, output short circuit -> protection trip -> latched gates off; "
                    "short removed, reset accepted, restart blocked by the precharge interlock",
        events=[
            Event(0.0, "start", label="startup"),
            Event(0.012, "load_resistance", r_full, "full load"),
            Event(0.025, "load_resistance", 0.3, "output short circuit (0.3 Ohm)"),
            Event(0.030, "load_resistance", r_full, "short removed"),
            Event(0.035, "fault_reset", label="fault reset"),
            Event(0.036, "start", label="restart attempt"),
        ])


def input_sag_scenario(design: ControlDesign) -> Scenario:
    r_full = design.v_ref ** 2 / design.nominal_power_W
    return Scenario(
        name="input_sag", t_end=0.040, v2_initial=0.875 * design.v_ref, r_load_initial=4 * r_full, i_load_initial=0.0,
        description="precharged start at 25 % load, full load, then the port-1 source sags to 450 V: the voltage loop drives the "
                    "phase shift to its limit, the current limit engages and the quasi-static series-current peak exceeds the "
                    "over-current threshold -> latched trip; the source recovers while the latch holds",
        events=[
            Event(0.0, "start", label="startup"),
            Event(0.012, "load_resistance", r_full, "full load"),
            Event(0.025, "source_voltage", 450.0, "port-1 sag 800 V -> 450 V"),
            Event(0.032, "source_voltage", design.plant.v1, "source restored (latch holds)"),
        ])


# ------------------------------------------------------------------- simulation

@dataclass
class SimulationResult:
    scenario: Scenario
    design_sha256: str
    traces: dict[str, np.ndarray]
    log: list[dict]
    trips: list[dict]
    metrics: dict
    final_mode: str

    def summary(self) -> dict:
        return {"scenario": self.scenario.to_dict(), "design_sha256": self.design_sha256, "final_mode": self.final_mode,
                "log": self.log, "trips": self.trips, "metrics": self.metrics,
                "samples": int(self.traces["t"].size), "duration_s": float(self.traces["t"][-1] + (self.traces["t"][1] - self.traces["t"][0]))}

    def to_dataset(self, design: ControlDesign) -> WaveformDataset:
        tr = self.traces
        ds = WaveformDataset(tr["t"], {}, {
            "format_note": "AIPE DAB SPS closed-loop host simulation (cycle-averaged plant, no switching waveforms)",
            "schema": SCHEMA, "design": design.to_dict(), "design_sha256": self.design_sha256,
            "scenario": self.scenario.to_dict(), "model_assumptions": list(MODEL_ASSUMPTIONS),
            "producer": {"id": "aipe.simulation-skills.control", "version": PACKAGE_VERSION}, "created_at": _now(),
            "modes": list(MODES),
        })
        ds.add("v2", tr["v2"], "V", "port-2 voltage at the sample instant")
        ds.add("v_ref", tr["v_ref"], "V", "effective (rate-limited) voltage reference")
        ds.add("i2", tr["i2"], "A", "cycle-averaged converter current into port 2 over the interval", "positive out of the converter into port 2")
        ds.add("i_load", tr["i_load"], "A", "load current drawn from port 2", "negative = injected (reverse power)")
        ds.add("i_ref", tr["i_ref"], "A", "current reference from the voltage loop (clamped)")
        ds.add("phi_cmd", tr["phi_cmd"], "rad", "phase-shift command computed in the sample", "phi > 0: secondary lags, power 1 -> 2")
        ds.add("phi_applied", tr["phi_applied"], "rad", "phase shift applied over the interval (after limit, slew, quantisation)")
        ds.add("p2", tr["p2"], "W", "power into port 2 (= power from port 1, lossless)")
        ds.add("i_l_peak", tr["i_l_peak"], "A", "quasi-static lossless series-current peak, primary referred")
        ds.add("v1_bus", tr["v1_bus"], "V", "port-1 bus voltage behind the source resistance")
        ds.add("mode", tr["mode"], "1", "supervisory mode index into metadata.modes")
        ds.add("gates_enabled", tr["enabled"], "1", "1 = modulator enabled, 0 = all gates off")
        ds.add("fault_latched", tr["fault"], "1", "1 = protection latch set")
        return ds


class HostSimulation:
    """Sampled closed-loop simulation of one scenario."""

    def __init__(self, design: ControlDesign, scenario: Scenario, controllers: Optional[ControllerSet] = None):
        problems = design.validate()
        if problems:
            raise ValueError("invalid control design: " + "; ".join(problems))
        self.design = design
        self.scenario = scenario
        self.ctl = controllers or design_controllers(design)
        params = replace(design.plant, r_load=scenario.r_load_initial, i_load=scenario.i_load_initial)
        self.plant = DabSpsPlant(params, scenario.v2_initial)
        self.mod = SpsModulator(design.modulator_config())
        self.pi = self.ctl.new_pi()
        self.df22 = self.ctl.new_df22()
        self.mode = "IDLE"
        self.latched = False
        self.v_ref_target = design.v_ref
        self.v_ref_eff = design.v_ref
        self.phi_cmd = 0.0
        self.phi_pending = 0.0
        self.phi_ramp = 0.0
        self.i_ref = 0.0
        self.t_mode = 0.0
        self.start_requested = False
        self.shutdown_requested = False
        self.log: list[dict] = []
        self.trips: list[dict] = []

    # ---- bookkeeping ----------------------------------------------------------
    def _log(self, t: float, kind: str, detail: str = "", **extra) -> None:
        self.log.append({"t": float(t), "kind": kind, "mode": self.mode, "detail": detail, **extra})

    def _transition(self, mode: str, t: float, detail: str) -> None:
        previous = self.mode
        self.mode = mode
        self.t_mode = t
        self._log(t, "transition", detail, from_mode=previous, to_mode=mode)

    def _trip(self, cause: str, t: float, meas: dict) -> None:
        self.latched = True
        record = {"t": float(t), "cause": cause, "v2_V": meas["v2"], "i2_A": meas["i2"], "i_l_peak_A": meas["i_l_peak"],
                  "mode_before": self.mode}
        self.trips.append(record)
        self._transition("FAULT", t, f"trip: {cause}")

    # ---- events -----------------------------------------------------------------
    def _apply_event(self, ev: Event, t: float) -> None:
        if ev.kind == "start":
            self.start_requested = True
        elif ev.kind == "load_resistance":
            self.plant.set_load(r_load=ev.value)
        elif ev.kind == "load_current":
            self.plant.set_load(i_load=float(ev.value))
        elif ev.kind == "setpoint":
            self.v_ref_target = float(ev.value)
        elif ev.kind == "shutdown":
            self.shutdown_requested = True
        elif ev.kind == "source_voltage":
            self.plant.p.v1 = float(ev.value)
            if self.plant.p.validate():
                raise ValueError("invalid source voltage event")
        elif ev.kind == "fault_reset":
            if self.mode == "FAULT":
                if self.plant.v2 <= self.design.protection.v2_over_V:
                    self.latched = False
                    self._transition("IDLE", t, "fault reset accepted: no condition present, gates remain off until a new start")
                else:
                    self._log(t, "fault_reset_rejected", "over-voltage condition still present")
            else:
                self._log(t, "fault_reset_ignored", "no fault latched")
        else:
            raise ValueError(f"unknown event kind {ev.kind!r}")
        self._log(t, "event", ev.label or ev.kind, event=ev.to_dict())

    # ---- protection and control -------------------------------------------------
    def _protect(self, meas: dict, t: float) -> None:
        if self.mode not in ACTIVE_MODES:
            return
        pr = self.design.protection
        if meas["i_l_peak"] > pr.i_l_peak_trip_A:
            self._trip("over_current_series_peak", t, meas)
        elif meas["v2"] > pr.v2_over_V:
            self._trip("over_voltage", t, meas)
        elif self.mode == "RUN" and meas["v2"] < pr.v2_under_V:
            self._trip("under_voltage", t, meas)

    def _control(self, meas: dict, t: float) -> None:
        d = self.design
        ts = d.ts
        v2, i2 = meas["v2"], meas["i2"]
        step = d.v_ref_slew_V_per_s * ts
        self.v_ref_eff += min(max(self.v_ref_target - self.v_ref_eff, -step), step)
        ramp_rate = math.radians(d.soft_start_rate_deg_per_ms) * 1e3  # rad/s
        phi_ss_max = math.radians(d.soft_start_phi_max_deg)
        if self.mode in ("IDLE", "OFF"):
            self.phi_cmd = 0.0
            self.i_ref = 0.0
            if self.start_requested:
                self.start_requested = False
                threshold = d.precharge_min_fraction * self.v_ref_target
                if v2 >= threshold:
                    self.phi_ramp = 0.0
                    self._transition("SOFT_START", t, f"start accepted: v2 = {v2:.1f} V >= precharge threshold {threshold:.1f} V")
                else:
                    self._log(t, "start_rejected", f"precharge interlock: v2 = {v2:.1f} V below {threshold:.1f} V")
        elif self.mode == "SOFT_START":
            self.phi_ramp = min(self.phi_ramp + ramp_rate * ts, phi_ss_max)
            self.phi_cmd = self.phi_ramp
            self.i_ref = 0.0  # no closed-loop reference during the open-loop ramp
            if v2 >= d.handover_fraction * self.v_ref_eff or self.phi_ramp >= phi_ss_max - 1e-12:
                self.pi.reset(u0=self.mod.phi_applied, error=0.0)
                self.df22.reset(y0=i2, error=self.v_ref_eff - v2)
                self._transition("RUN", t, f"bumpless hand-over to closed loop at v2 = {v2:.1f} V, phi = {math.degrees(self.mod.phi_applied):.2f} deg")
            elif t - self.t_mode > d.protection.soft_start_timeout_s:
                self._trip("soft_start_timeout", t, meas)
        elif self.mode == "RUN":
            self.i_ref = self.df22.step(self.v_ref_eff - v2)
            # tracking anti-windup against the modulator's command/slew limits (value applied for the previous output)
            self.phi_cmd = self.pi.step(self.i_ref - i2, u_applied=self.mod.phi_limited if self.mod.enabled else None)
            if self.shutdown_requested:
                self.shutdown_requested = False
                self.phi_ramp = self.phi_cmd
                self._transition("SHUTDOWN", t, "controlled shutdown: phase-shift ramp to zero")
        elif self.mode == "SHUTDOWN":
            delta = min(ramp_rate * ts, abs(self.phi_ramp))
            self.phi_ramp -= math.copysign(delta, self.phi_ramp) if self.phi_ramp else 0.0
            self.phi_cmd = self.phi_ramp
            self.i_ref = 0.0
            if self.phi_ramp == 0.0:
                self._transition("OFF", t, "phase shift at zero: gates disabled from the next period")
        elif self.mode == "FAULT":
            self.phi_cmd = 0.0
            self.i_ref = 0.0

    # ---- main loop ---------------------------------------------------------------
    def run(self) -> SimulationResult:
        d = self.design
        ts = d.ts
        n = int(round(self.scenario.t_end / ts))
        if n < 2:
            raise ValueError("scenario too short")
        names = ("t", "v2", "v_ref", "i2", "i_load", "i_ref", "phi_cmd", "phi_applied", "p2", "i_l_peak", "v1_bus", "mode", "enabled", "fault")
        tr = {name: np.zeros(n) for name in names}
        events = sorted(self.scenario.events, key=lambda e: e.t)
        next_event = 0
        for k in range(n):
            t = k * ts
            while next_event < len(events) and events[next_event].t <= t + 1e-12:
                self._apply_event(events[next_event], t)
                next_event += 1
            meas = self.plant.measurements()
            self._protect(meas, t)
            if d.computation_delay_samples == 0:
                # idealised: the value computed in this sample is applied in the same interval
                self._control(meas, t)
                enable = self.mode in ACTIVE_MODES
                phi_applied = self.mod.command(self.phi_cmd, enable)
            else:
                # shadow-register load at the period boundary with the value computed during the previous period,
                # then the ISR computes the next value (a trip detected above disables the gates immediately)
                enable = self.mode in ACTIVE_MODES
                phi_applied = self.mod.command(self.phi_pending, enable)
                self._control(meas, t)
                self.phi_pending = self.phi_cmd
            out = self.plant.step(phi_applied, enabled=enable)
            tr["t"][k] = t
            tr["v2"][k] = meas["v2"]
            tr["v_ref"][k] = self.v_ref_eff
            tr["i2"][k] = out["i2"]
            tr["i_load"][k] = out["i_load"]
            tr["i_ref"][k] = self.i_ref
            tr["phi_cmd"][k] = self.phi_cmd
            tr["phi_applied"][k] = phi_applied
            tr["p2"][k] = out["p2"]
            tr["i_l_peak"][k] = out["i_l_peak"]
            tr["v1_bus"][k] = out["v1_bus"]
            tr["mode"][k] = MODES.index(self.mode)
            tr["enabled"][k] = 1.0 if enable else 0.0
            tr["fault"][k] = 1.0 if self.latched else 0.0
        result = SimulationResult(self.scenario, d.sha256(), tr, self.log, self.trips, {}, self.mode)
        result.metrics = compute_metrics(result, d)
        return result


# ---------------------------------------------------------------------- metrics

def _window_metrics(tr: dict[str, np.ndarray], mask: np.ndarray, band_fraction: float = 0.01) -> dict:
    t, v2, vref = tr["t"][mask], tr["v2"][mask], tr["v_ref"][mask]
    dev = v2 - vref
    scale = float(vref[-1]) if vref[-1] else 1.0
    inside = np.abs(dev) <= band_fraction * np.abs(vref)
    recovery = None
    if inside.size and inside[-1]:
        last_outside = np.where(~inside)[0]
        recovery = float(t[last_outside[-1] + 1] - t[0]) if last_outside.size else 0.0
    tail = max(int(0.1 * t.size), 1)
    return {
        "t_start_s": float(t[0]), "t_end_s": float(t[-1]), "v2_max_V": float(v2.max()), "v2_min_V": float(v2.min()),
        "max_overshoot_V": float(max(dev.max(), 0.0)), "max_undershoot_V": float(max(-dev.min(), 0.0)),
        "max_deviation_V": float(np.abs(dev).max()), "max_deviation_pct": float(np.abs(dev).max() / scale * 100),
        "recovery_time_to_1pct_s": recovery, "final_error_V": float(np.mean(dev[-tail:])),
        "i2_max_A": float(tr["i2"][mask].max()), "i2_min_A": float(tr["i2"][mask].min()),
        "i_ref_max_A": float(tr["i_ref"][mask].max()), "i_ref_min_A": float(tr["i_ref"][mask].min()),
        "phi_applied_max_deg": float(np.degrees(tr["phi_applied"][mask].max())), "phi_applied_min_deg": float(np.degrees(tr["phi_applied"][mask].min())),
        "p2_max_W": float(tr["p2"][mask].max()), "p2_min_W": float(tr["p2"][mask].min()),
        "i_l_peak_max_A": float(tr["i_l_peak"][mask].max()), "mode_at_end": MODES[int(tr["mode"][mask][-1])],
    }


def compute_metrics(result: SimulationResult, design: ControlDesign) -> dict:
    tr = result.traces
    t = tr["t"]
    labelled = [e for e in sorted(result.scenario.events, key=lambda e: e.t) if e.label]
    windows = {}
    for i, ev in enumerate(labelled):
        t0 = ev.t
        t1 = labelled[i + 1].t if i + 1 < len(labelled) else float(t[-1]) + design.ts
        mask = (t >= t0 - 1e-12) & (t < t1 - 1e-12)
        if mask.sum() >= 2:
            windows[ev.label] = _window_metrics(tr, mask)
    handover = next((e["t"] for e in result.log if e.get("to_mode") == "RUN"), None)
    # gates-off instant from the trace: first disabled interval after the gates were first enabled
    # (a mode transition logged in sample k disables the gates from the register load at sample k + 1)
    enabled = tr["enabled"] > 0.5
    gates_off = None
    first_on = np.argmax(enabled) if enabled.any() else None
    if first_on is not None:
        later_off = np.where(~enabled & (np.arange(enabled.size) > first_on))[0]
        gates_off = float(t[later_off[0]]) if later_off.size else None
    run_mask = tr["mode"] == MODES.index("RUN")
    startup = None
    if handover is not None:
        later = [e.t for e in labelled if e.t > handover + 1e-12]
        t_end = later[0] if later else float(t[-1]) + design.ts
        mask = (t >= handover - 1e-12) & (t < t_end - 1e-12)
        before = t < handover - 1e-12
        if mask.sum() >= 2:
            w = _window_metrics(tr, mask)
            idx = int(np.argmax(t >= handover - 1e-12))
            startup = {"handover_time_s": handover, "v2_at_handover_V": float(tr["v2"][idx]),
                       "phi_at_handover_deg": float(np.degrees(tr["phi_applied"][idx])),
                       "soft_start_v2_min_V": float(tr["v2"][before].min()) if before.any() else None,
                       "soft_start_i2_max_A": float(tr["i2"][before].max()) if before.any() else None,
                       "overshoot_after_handover_V": w["max_overshoot_V"], "settling_time_to_1pct_after_handover_s": w["recovery_time_to_1pct_s"],
                       "final_error_V": w["final_error_V"]}
    metrics = {
        "handover_time_s": handover, "gates_off_time_s": gates_off, "final_mode": result.final_mode, "startup": startup,
        "i_ref_abs_max_A": float(np.abs(tr["i_ref"]).max()), "i_ref_limit_A": design.i_ref_limit_A,
        "i_ref_within_limit": bool(np.abs(tr["i_ref"]).max() <= design.i_ref_limit_A * (1 + 1e-9)),
        "i2_abs_max_A": float(np.abs(tr["i2"]).max()),
        "phi_applied_abs_max_deg": float(np.degrees(np.abs(tr["phi_applied"]).max())), "phi_max_deg": design.phi_max_deg,
        "i_l_peak_max_A": float(tr["i_l_peak"].max()), "i_l_peak_trip_A": design.protection.i_l_peak_trip_A,
        "v2_max_V": float(tr["v2"].max()), "v2_min_V": float(tr["v2"].min()),
        "v2_max_in_run_V": float(tr["v2"][run_mask].max()) if run_mask.any() else None,
        "v2_min_in_run_V": float(tr["v2"][run_mask].min()) if run_mask.any() else None,
        "trips": result.trips, "windows": windows,
        "quantisation_steps_in_phi_applied": int(np.unique(np.round(tr["phi_applied"], 12)).size),
    }
    return metrics


# ---------------------------------------------------------------------- figures

def plot_closed_loop(result: SimulationResult, design: ControlDesign, path: Union[str, Path]) -> str:
    from ..waveforms.plots import REFERENCE, SERIES, TEXT, TEXT_SECONDARY, _legend, _mpl

    plt = _mpl()
    tr = result.traces
    t_ms = tr["t"] * 1e3
    fig, axes = plt.subplots(6, 1, figsize=(10, 15), sharex=True)
    ax = axes[0]
    ax.plot(t_ms, tr["v2"], color=SERIES[0], label="v2 port-2 voltage")
    ax.plot(t_ms, tr["v_ref"], color=SERIES[1], linestyle="--", label="v_ref (rate-limited)")
    ax.axhline(design.protection.v2_over_V, color=REFERENCE, linewidth=0.8, linestyle=":", label="OV / UV trip")
    ax.axhline(design.protection.v2_under_V, color=REFERENCE, linewidth=0.8, linestyle=":")
    ax.set_ylabel("voltage (V)")
    ax.set_title("Output voltage")
    _legend(ax, 3)
    ax = axes[1]
    ax.plot(t_ms, tr["i2"], color=SERIES[0], label="i2 converter current (cycle average)")
    ax.plot(t_ms, tr["i_load"], color=SERIES[1], label="i_load")
    ax.plot(t_ms, tr["i_ref"], color=SERIES[2], linestyle="--", label="i_ref voltage-loop output")
    ax.axhline(design.i_ref_limit_A, color=REFERENCE, linewidth=0.8, linestyle=":", label="±I_lim")
    ax.axhline(-design.i_ref_limit_A, color=REFERENCE, linewidth=0.8, linestyle=":")
    ax.set_ylabel("current (A)")
    ax.set_title("Port-2 currents (positive = into port 2)")
    _legend(ax, 4)
    ax = axes[2]
    ax.plot(t_ms, np.degrees(tr["phi_cmd"]), color=SERIES[0], label="phi command")
    ax.plot(t_ms, np.degrees(tr["phi_applied"]), color=SERIES[1], linestyle="--", label="phi applied (limited, slewed, quantised)")
    ax.axhline(design.phi_max_deg, color=REFERENCE, linewidth=0.8, linestyle=":", label="±phi_max")
    ax.axhline(-design.phi_max_deg, color=REFERENCE, linewidth=0.8, linestyle=":")
    ax.set_ylabel("phase shift (deg)")
    ax.set_title("Phase shift (phi > 0: power port 1 → port 2)")
    _legend(ax, 3)
    ax = axes[3]
    ax.plot(t_ms, tr["p2"] / 1e3, color=SERIES[0], label="p2 power into port 2")
    ax.set_ylabel("power (kW)")
    ax.set_title("Transferred power (lossless model)")
    _legend(ax, 1)
    ax = axes[4]
    ax.plot(t_ms, tr["i_l_peak"], color=SERIES[0], label="series-current peak, quasi-static lossless estimate")
    ax.axhline(design.protection.i_l_peak_trip_A, color=REFERENCE, linewidth=0.8, linestyle=":", label="over-current trip")
    ax.set_ylabel("current (A)")
    ax.set_title("Primary-referred series current peak")
    _legend(ax, 2)
    ax = axes[5]
    ax.step(t_ms, tr["mode"], where="post", color=SERIES[0], label="supervisory mode")
    off = tr["enabled"] < 0.5
    if off.any():
        edges = np.diff(np.concatenate([[0], off.astype(int), [0]]))
        for start, stop in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
            ax.axvspan(t_ms[start], t_ms[min(stop, t_ms.size - 1)], color=REFERENCE, alpha=0.15, linewidth=0)
        ax.plot([], [], color=REFERENCE, alpha=0.4, linewidth=8, label="all gates off")
    ax.set_yticks(range(len(MODES)))
    ax.set_yticklabels(MODES)
    ax.set_ylabel("mode")
    ax.set_xlabel("time (ms)")
    ax.set_title("Supervisory state")
    _legend(ax, 2)
    for ev in result.scenario.events:
        if ev.label:
            for a in axes:
                a.axvline(ev.t * 1e3, color=REFERENCE, linewidth=0.6, alpha=0.6)
            axes[0].text(ev.t * 1e3, axes[0].get_ylim()[1], ev.label, rotation=90, fontsize=6.5, color=TEXT_SECONDARY, va="top", ha="right")
    fig.suptitle(f"DAB SPS closed-loop host simulation — scenario '{result.scenario.name}' — design {result.design_sha256[:12]}",
                 x=0.02, ha="left", fontsize=10, color=TEXT)
    p = design.plant
    fig.text(0.02, 0.004, f"{p.v1:g} V → {design.v_ref:g} V, f_sw = {p.f_sw / 1e3:g} kHz, n = {p.n_ratio:g}, L = {p.l_total * 1e6:g} µH, "
             f"C2 = {p.c2 * 1e6:g} µF; voltage loop {design.f_c_voltage_Hz:g} Hz / {design.pm_voltage_deg:g}°, current loop {design.f_c_current_Hz:g} Hz; "
             f"cycle-averaged lossless plant, no firmware executed", fontsize=8, color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.015, 1, 0.975))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def plot_gate_pattern(design: ControlDesign, path: Union[str, Path], phi_before_deg: float = 10.0, phi_after_deg: float = 20.0) -> str:
    """Eight gate signals over four periods with a phase-register step after period 1 (illustration; slew limit relaxed)."""
    from ..waveforms.plots import REFERENCE, SERIES, TEXT, TEXT_SECONDARY, _legend, _mpl

    plt = _mpl()
    cfg = replace(design.modulator_config(), slew_max_rad_per_update=math.radians(90.0), phi_max_rad=math.radians(89.0))
    mod = SpsModulator(cfg)
    for phi in (phi_before_deg, phi_before_deg, phi_after_deg, phi_after_deg):
        mod.command(math.radians(phi))
    T = cfg.period
    t = np.linspace(-T / 2, 3.5 * T, 8001)
    g = mod.gate_states(t)
    b = mod.bridge_states(t)
    t_us = t * 1e6
    fig, axes = plt.subplots(5, 1, figsize=(10, 11), sharex=True)
    for ax, (hi, lo, leg) in zip(axes[:4], (("S1", "S2", "A (primary)"), ("S3", "S4", "B (primary)"), ("S5", "S6", "C (secondary)"), ("S7", "S8", "D (secondary)"))):
        ax.step(t_us, g[hi].astype(float), where="post", color=SERIES[0], label=f"{hi} high side")
        ax.step(t_us, g[lo].astype(float) + 1.5, where="post", color=SERIES[1], label=f"{lo} low side (offset +1.5)")
        ax.set_yticks([0, 1, 1.5, 2.5])
        ax.set_yticklabels(["off", "on", "off", "on"])
        ax.set_ylabel("gate (logic)")
        ax.set_title(f"Leg {leg}: dead time {cfg.dead_time_realised * 1e9:g} ns")
        _legend(ax, 2)
    ax = axes[4]
    ax.step(t_us, b["v_ab"], where="post", color=SERIES[0], label="v_ab / V1")
    ax.step(t_us, b["v_cd"], where="post", color=SERIES[1], linestyle="--", label="v_cd / V2 (secondary)")
    for inst in mod.ideal_switching_instants("primary", 3.5 * T, -T / 2):
        ax.axvline(inst["t"] * 1e6, color=REFERENCE, linewidth=0.6, linestyle=":")
    ax.set_ylabel("normalised voltage (1)")
    ax.set_xlabel("time (µs), t = 0 at the centre of the primary positive half-cycle")
    ax.set_title(f"Bridge voltages: phi = {phi_before_deg:g}° in periods 0-1, {phi_after_deg:g}° from period 2 (register load at the period boundary); 0 during dead time")
    _legend(ax, 2)
    fig.suptitle(f"SPS modulator gate pattern — {cfg.pwm_clock_hz / 1e6:g} MHz time base, TBPRD = {cfg.tbprd:g}, "
                 f"fine step {(cfg.hr_step_s or cfg.coarse_step) * 1e12:g} ps", x=0.02, ha="left", fontsize=10, color=TEXT)
    fig.text(0.02, 0.004, "Model of the gate pattern only (no switching waveforms); phi > 0: secondary lags, power port 1 → port 2",
             fontsize=8, color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.015, 1, 0.975))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


# ------------------------------------------------------------------- orchestration

SCENARIOS = {"nominal": nominal_scenario, "fault": fault_scenario, "input_sag": input_sag_scenario}


def run_scenario(design: ControlDesign, scenario: Union[str, Scenario], controllers: Optional[ControllerSet] = None) -> SimulationResult:
    if isinstance(scenario, str):
        scenario = SCENARIOS[scenario](design)
    return HostSimulation(design, scenario, controllers).run()


def write_results(design: ControlDesign, controllers: ControllerSet, results: dict[str, SimulationResult],
                  out_dir: Union[str, Path], figures: bool = True) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "schema": SCHEMA, "created_at": _now(),
        "producer": {"id": "aipe.simulation-skills.control", "version": PACKAGE_VERSION},
        "design": design.to_dict(), "design_sha256": design.sha256(), "model_assumptions": list(MODEL_ASSUMPTIONS),
        "modulator": design.modulator_config().describe(), "controllers": controllers.report, "scenarios": {},
        "limitations": [
            "Cycle-averaged lossless plant: no switching waveforms, no losses, no magnetising current, no sensor/ADC model.",
            "Protection acts with up to one period of latency on quasi-static analytic currents; hardware trips act within the period.",
            "No firmware was built or executed; controller coefficients are host-side design values.",
        ],
    }
    for name, result in results.items():
        ds = result.to_dataset(design)
        h5 = out / f"traces_{name}.h5"
        ds.save_hdf5(h5)
        entry = result.summary()
        entry["traces"] = {"path": str(h5), "dataset_sha256": ds.sha256(), "channels": ds.channel_index()}
        entry["figure"] = None
        if figures:
            try:
                entry["figure"] = plot_closed_loop(result, design, out / f"closed_loop_{name}.png")
            except ImportError as exc:  # matplotlib is optional
                entry["figure_note"] = f"figure skipped: {exc}"
        summary["scenarios"][name] = entry
    summary["gate_pattern_figure"] = None
    if figures:
        try:
            summary["gate_pattern_figure"] = plot_gate_pattern(design, out / "gate_pattern.png")
        except ImportError as exc:
            summary["gate_pattern_figure_note"] = f"figure skipped: {exc}"
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    summary["summary_path"] = str(out / "summary.json")
    return summary


def run_baseline(design: Optional[ControlDesign] = None, out_dir: Optional[Union[str, Path]] = None,
                 scenarios: tuple[str, ...] = ("nominal", "fault", "input_sag"), figures: bool = True) -> dict:
    """Design the controllers, run the canonical scenarios and (optionally) write the artefacts."""
    design = design or ControlDesign()
    controllers = design_controllers(design)
    results = {name: run_scenario(design, name, controllers) for name in scenarios}
    if out_dir is None:
        return {"schema": SCHEMA, "design_sha256": design.sha256(), "controllers": controllers.report,
                "scenarios": {name: r.summary() for name, r in results.items()}, "results": results}
    summary = write_results(design, controllers, results, out_dir, figures)
    summary["results"] = results
    return summary


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")
