"""Discrete single-phase-shift (SPS) modulator model for the eight DAB gate signals.

The model reproduces what a digital PWM peripheral does with a phase-shift
command: it limits and rate-limits the command, quantises it to the timer
resolution, holds it for whole switching periods (shadow-register load at the
period boundary) and derives the eight complementary gate signals with dead
time from one common time base.

Time base and sign convention (identical to :mod:`aipe_simulation.dab.gating`)
------------------------------------------------------------------------------
* ``t = 0`` is the centre of the primary positive half-cycle (S1 and S4 on).
  Switching period ``m`` covers ``[(m - 1/2) T, (m + 1/2) T)``; its register
  values are the ones loaded at the period boundary ``(m - 1/2) T`` (the
  up-down counter zero of the primary time base, i.e. the centre of the
  negative half-cycle).
* Primary ideal switching instants: ``m T - T/4`` (``v_ab``: -V1 -> +V1) and
  ``m T + T/4`` (+V1 -> -V1); the secondary instants are the same shifted by
  ``t_phi = phi / (2 pi) T``. ``phi > 0``: secondary lags, power flows from
  port 1 to port 2; ``phi < 0`` reverses the power flow.
* Leg A (S1 high, S2 low) and leg B (S3 high, S4 low) run from the same time
  base with their outputs swapped (leg-to-leg 180 degrees), so S4 carries the
  S1 pattern and S3 the S2 pattern; likewise S8/S5 and S7/S6 on the secondary.
* Dead band ``t_dead`` per leg transition. ``dead_band_mode="centred"`` places
  the ideal instant at the centre of the dead band (outgoing switch off
  ``t_dead/2`` before, incoming switch on ``t_dead/2`` after), exactly like
  :class:`~aipe_simulation.dab.gating.SpsTiming`. ``"delayed_turn_on"`` delays
  only the turn-on edges by the full ``t_dead`` (rising-edge/falling-edge
  delay as in a PWM dead-band submodule); the whole pattern of both bridges
  is then shifted by ``t_dead/2``, which leaves the phase shift unchanged.

Quantisation
------------
The phase shift is realised as a register of whole time-base clocks
(``1 / pwm_clock_hz``) plus high-resolution steps (``hr_step_s``), so the
realisable grid is ``{m / f_clk + k hr_step}``. Dead time is quantised to whole
time-base clocks. With ``quantise=False`` the model is ideal (useful to
cross-check against :class:`SpsTiming` exactly).

The TI reference design TIDA-010054 realises SPS with four ePWM modules in
up-down count mode, TBPRD = 500 at 100 kHz, a high-resolution phase register
for the secondary bridge and a 200 ns dead band (TI design guide TIDUES0; see
``AIPE-Workflows/examples/dab-10kw/references/tida-010054-fact-sheet.md``).
The defaults below (100 MHz time base, 150 ps fine step) are AIPE modelling
choices consistent with TBPRD = 500 at 100 kHz; they are not TI statements.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np

from ..dab.gating import HIGH_SIDE, LEG_OF, PRIMARY, SWITCHES, SpsTiming

POSITIVE_PATTERN = ("S1", "S4", "S5", "S8")  # on during the positive half-cycle of their bridge voltage
DEAD_BAND_MODES = ("centred", "delayed_turn_on")
_TOL = 1e-15  # absolute time tolerance for inclusive window boundaries (T = 10 us)


@dataclass(frozen=True)
class SpsModulatorConfig:
    """Modulator and timer parameters (SI units)."""

    f_sw: float = 100e3  # Hz, switching frequency
    pwm_clock_hz: float = 100e6  # Hz, time-base clock; up-down count => TBPRD = f_clk / (2 f_sw)
    hr_step_s: Optional[float] = 150e-12  # s, high-resolution phase step; None = coarse clock only
    dead_time: float = 200e-9  # s, per leg transition
    phi_max_rad: float = math.radians(45.0)  # command limit (both directions)
    slew_max_rad_per_update: float = math.radians(1.0)  # rate limit per register update (1 deg = 27.8 ns at 100 kHz)
    update_divider: int = 1  # the register accepts a new value every N switching periods
    quantise: bool = True  # False = ideal (continuous) phase and dead time
    dead_band_mode: str = "centred"

    @property
    def period(self) -> float:
        return 1.0 / self.f_sw

    @property
    def coarse_step(self) -> float:
        return 1.0 / self.pwm_clock_hz

    @property
    def tbprd(self) -> float:
        """Up-down counter period register implied by the clock and f_sw."""
        return self.pwm_clock_hz / (2.0 * self.f_sw)

    @property
    def phase_resolution(self) -> float:
        """Finest realisable phase-shift time step (s)."""
        if not self.quantise:
            return 0.0
        return self.hr_step_s if self.hr_step_s else self.coarse_step

    @property
    def phase_resolution_rad(self) -> float:
        return self.phase_resolution / self.period * 2 * math.pi

    @property
    def dead_time_realised(self) -> float:
        if not self.quantise:
            return self.dead_time
        return round(self.dead_time * self.pwm_clock_hz) * self.coarse_step

    @property
    def slew_time_per_update(self) -> float:
        return self.slew_max_rad_per_update / (2 * math.pi) * self.period

    def validate(self) -> list[str]:
        problems = []
        if self.f_sw <= 0 or self.pwm_clock_hz <= 0:
            problems.append("f_sw and pwm_clock_hz must be positive")
            return problems
        if self.hr_step_s is not None and not (0 < self.hr_step_s < self.coarse_step):
            problems.append("hr_step_s must be positive and smaller than the time-base clock period")
        if self.dead_time < 0 or self.dead_time >= self.period / 4:
            problems.append("dead_time must be non-negative and smaller than a quarter period")
        if not (0 < self.phi_max_rad < math.pi / 2):
            problems.append("phi_max_rad must lie in (0, pi/2): the SPS law is defined for |phi| <= pi/2 and the per-period gate pattern needs |t_phi| < T/4")
        if self.slew_max_rad_per_update <= 0:
            problems.append("slew_max_rad_per_update must be positive")
        if self.slew_time_per_update + self.dead_time >= self.period / 2:
            problems.append("slew per update plus dead time must stay below half a period to keep every on-interval positive")
        if self.update_divider < 1:
            problems.append("update_divider must be at least 1")
        if self.dead_band_mode not in DEAD_BAND_MODES:
            problems.append(f"dead_band_mode must be one of {DEAD_BAND_MODES}")
        if self.quantise and abs(self.tbprd - round(self.tbprd)) > 1e-9:
            problems.append(f"pwm_clock_hz / (2 f_sw) = {self.tbprd:.6g} must be an integer period register value")
        return problems

    def describe(self) -> dict:
        return {
            "modulation": "single-phase-shift",
            "time_origin": "centre of primary positive half-cycle (S1, S4 on); register load at the period boundary (m - 1/2) T",
            "sign_convention": "phi > 0: secondary lags primary, power flows from port 1 to port 2",
            "f_sw_Hz": self.f_sw, "period_s": self.period,
            "pwm_clock_Hz": self.pwm_clock_hz, "coarse_step_s": self.coarse_step, "tbprd_counts": self.tbprd,
            "hr_step_s": self.hr_step_s, "quantise": self.quantise,
            "phase_resolution_s": self.phase_resolution, "phase_resolution_deg": math.degrees(self.phase_resolution_rad),
            "dead_time_s": self.dead_time, "dead_time_realised_s": self.dead_time_realised,
            "dead_time_counts": round(self.dead_time * self.pwm_clock_hz) if self.quantise else None,
            "dead_band_mode": self.dead_band_mode,
            "phi_max_deg": math.degrees(self.phi_max_rad), "t_phi_max_s": self.phi_max_rad / (2 * math.pi) * self.period,
            "slew_max_deg_per_update": math.degrees(self.slew_max_rad_per_update), "update_divider": self.update_divider,
            "leg_to_leg": "leg B/D outputs are the swapped leg A/C outputs (180 degrees); S4=S1, S3=S2, S8=S5, S7=S6 patterns",
        }

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PhaseRegister:
    """Realised phase-shift register content."""

    direction: int  # +1 secondary lags (power 1 -> 2), -1 secondary leads, 0 zero shift
    coarse_counts: int  # whole time-base clocks of |t_phi|
    fine_steps: int  # high-resolution steps on top of the coarse counts
    t_phi: float  # s, signed realised phase-shift time
    phi_rad: float  # rad, signed realised phase shift
    quantised: bool

    def to_dict(self) -> dict:
        return {**asdict(self), "phi_deg": math.degrees(self.phi_rad)}


class SpsModulator:
    """Stateful SPS modulator: one :meth:`command` per switching period."""

    def __init__(self, config: Optional[SpsModulatorConfig] = None):
        self.cfg = config or SpsModulatorConfig()
        problems = self.cfg.validate()
        if problems:
            raise ValueError("invalid SPS modulator configuration: " + "; ".join(problems))
        self.reset()

    # ---- register handling --------------------------------------------------
    def reset(self) -> None:
        self.register = PhaseRegister(0, 0, 0, 0.0, 0.0, self.cfg.quantise)
        self.phi_applied = 0.0
        self.phi_limited = 0.0  # after command and slew limiting, before quantisation (anti-windup feedback value)
        self.enabled = False
        self.limited = False
        self.slew_limited = False
        self._calls = 0
        self._schedule: list[tuple[float, bool]] = []  # per period: (t_phi, enabled)

    def quantise_phase(self, phi_rad: float) -> PhaseRegister:
        """Map a (limited) phase-shift command to the realisable register grid."""
        cfg = self.cfg
        t = phi_rad / (2 * math.pi) * cfg.period
        direction = 0 if t == 0.0 else (1 if t > 0 else -1)
        mag = abs(t)
        if not cfg.quantise:
            coarse = int(math.floor(mag / cfg.coarse_step + 1e-9))
            return PhaseRegister(direction, coarse, 0, t, phi_rad, False)
        cs = cfg.coarse_step
        if cfg.hr_step_s is None:
            coarse = int(round(mag / cs))
            fine = 0
            realised = coarse * cs
        else:
            hs = cfg.hr_step_s
            coarse = int(math.floor(mag / cs + 1e-9))
            rem = mag - coarse * cs
            fine_max = int(math.floor(cs / hs + 1e-9))
            fine = min(int(round(rem / hs)), fine_max)
            cand_a = coarse * cs + fine * hs
            cand_b = (coarse + 1) * cs
            if abs(cand_b - mag) < abs(cand_a - mag):
                coarse, fine, realised = coarse + 1, 0, cand_b
            else:
                realised = cand_a
        t_q = direction * realised
        phi_q = t_q / cfg.period * 2 * math.pi
        if realised == 0.0:
            direction = 0
        return PhaseRegister(direction, coarse, fine, t_q, phi_q, True)

    def command(self, phi_cmd: float, enable: bool = True) -> float:
        """Register update for the next switching period.

        Applies the command limit, the slew limit (relative to the value
        currently applied) and the timer quantisation; returns the applied
        phase shift in radians (0 when the gates are disabled). With
        ``enable=False`` all gates are off for the period and the slew limiter
        restarts from zero on the next enable (a restart is always a ramp).
        """
        cfg = self.cfg
        self._calls += 1
        if not math.isfinite(phi_cmd):
            raise ValueError("phase-shift command must be finite")
        if not enable:
            self.register = PhaseRegister(0, 0, 0, 0.0, 0.0, cfg.quantise)
            self.phi_applied = 0.0
            self.phi_limited = 0.0
            self.enabled = False
            self.limited = False
            self.slew_limited = False
        else:
            if (self._calls - 1) % cfg.update_divider == 0 or not self.enabled:
                phi = min(max(phi_cmd, -cfg.phi_max_rad), cfg.phi_max_rad)
                self.limited = phi != phi_cmd
                delta = phi - self.phi_applied
                step = min(max(delta, -cfg.slew_max_rad_per_update), cfg.slew_max_rad_per_update)
                self.slew_limited = step != delta
                self.phi_limited = self.phi_applied + step
                self.register = self.quantise_phase(self.phi_limited)
                self.phi_applied = self.register.phi_rad
            self.enabled = True
        self._schedule.append((self.register.t_phi if self.enabled else 0.0, self.enabled))
        return self.phi_applied

    def timing(self) -> SpsTiming:
        """Equivalent ideal periodic timing of the currently applied register (centred dead band)."""
        return SpsTiming(self.cfg.f_sw, self.phi_applied, self.cfg.dead_time_realised)

    @property
    def periods_scheduled(self) -> int:
        return len(self._schedule)

    def schedule(self) -> list[dict]:
        return [{"period": m, "t_phi_s": t, "phi_deg": math.degrees(t / self.cfg.period * 2 * math.pi), "enabled": en}
                for m, (t, en) in enumerate(self._schedule)]

    # ---- waveform generation ------------------------------------------------
    def _entry(self, m: int) -> tuple[float, bool]:
        if not self._schedule:
            return 0.0, False
        return self._schedule[min(max(m, 0), len(self._schedule) - 1)]

    def _period_index(self, t: float) -> int:
        T = self.cfg.period
        return int(math.floor((t + T / 2) / T + 1e-12))

    def _instants(self, bridge: str, m_lo: int, m_hi: int) -> list[tuple[float, int]]:
        T = self.cfg.period
        out = []
        for m in range(m_lo, m_hi + 1):
            t_phi, _ = self._entry(m)
            shift = t_phi if bridge == "secondary" else 0.0
            out.append((m * T - T / 4 + shift, +1))
            out.append((m * T + T / 4 + shift, -1))
        return out

    def ideal_switching_instants(self, bridge: str, t_end: float, t_start: float = 0.0) -> list[dict]:
        """Bridge-voltage transitions in ``[t_start, t_end]`` (``direction`` +1: -V -> +V)."""
        if bridge not in ("primary", "secondary"):
            raise ValueError("bridge must be 'primary' or 'secondary'")
        m_lo, m_hi = self._period_index(t_start) - 1, self._period_index(t_end) + 1
        out = []
        for t, d in self._instants(bridge, m_lo, m_hi):
            _, enabled = self._entry(self._period_index(t))
            if enabled and t_start - _TOL <= t <= t_end + _TOL:
                out.append({"t": t, "direction": d})
        return out

    def _clip_disabled(self, a: float, b: float) -> list[tuple[float, float]]:
        T = self.cfg.period
        pieces = [(a, b)]
        for m in range(self._period_index(a), self._period_index(b) + 1):
            if self._entry(m)[1]:
                continue
            lo, hi = m * T - T / 2, m * T + T / 2
            nxt = []
            for pa, pb in pieces:
                if pb <= lo or pa >= hi:
                    nxt.append((pa, pb))
                    continue
                if pa < lo:
                    nxt.append((pa, lo))
                if pb > hi:
                    nxt.append((hi, pb))
            pieces = nxt
        return pieces

    def on_intervals(self, switch: str, t_start: float, t_end: float) -> list[tuple[float, float]]:
        """Gate-on intervals ``[(t_on, t_off), ...]`` of ``switch`` overlapping ``[t_start, t_end]``."""
        if switch not in SWITCHES:
            raise ValueError(f"unknown switch {switch!r}")
        cfg = self.cfg
        td = cfg.dead_time_realised
        d_on, d_off = (td / 2, td / 2) if cfg.dead_band_mode == "centred" else (td, 0.0)
        bridge = "primary" if switch in PRIMARY else "secondary"
        want = +1 if switch in POSITIVE_PATTERN else -1
        m_lo, m_hi = self._period_index(t_start) - 2, self._period_index(t_end) + 2
        inst = self._instants(bridge, m_lo, m_hi)
        out = []
        for (ti, di), (tj, _) in zip(inst[:-1], inst[1:]):
            if di != want:
                continue
            for a, b in self._clip_disabled(ti + d_on, tj - d_off):
                if b > a + _TOL and b >= t_start - _TOL and a <= t_end + _TOL:
                    out.append((a, b))
        return out

    def rising_edges(self, switch: str, t_end: float, t_start: float = 0.0) -> list[float]:
        return [a for a, _ in self.on_intervals(switch, t_start, t_end) if t_start - _TOL <= a <= t_end + _TOL]

    def falling_edges(self, switch: str, t_end: float, t_start: float = 0.0) -> list[float]:
        return [b for _, b in self.on_intervals(switch, t_start, t_end) if t_start - _TOL <= b <= t_end + _TOL]

    def gate_states(self, t) -> dict[str, np.ndarray]:
        """Boolean gate state of every switch at the sample times ``t`` (edge instants count as off/on: ``t_on <= t < t_off``)."""
        t = np.atleast_1d(np.asarray(t, dtype=np.float64))
        if t.size == 0:
            return {s: np.zeros(0, dtype=bool) for s in SWITCHES}
        t0, t1 = float(t.min()), float(t.max())
        states = {}
        for s in SWITCHES:
            iv = self.on_intervals(s, t0, t1)
            if not iv:
                states[s] = np.zeros(t.shape, dtype=bool)
                continue
            starts = np.array([a for a, _ in iv])
            ends = np.array([b for _, b in iv])
            idx = np.searchsorted(starts, t, side="right") - 1
            ok = idx >= 0
            state = np.zeros(t.shape, dtype=bool)
            state[ok] = t[ok] < ends[idx[ok]]
            states[s] = state
        return states

    def bridge_states(self, t) -> dict[str, np.ndarray]:
        """Normalised bridge voltages (+1, -1, 0 during dead time) derived from the gate states."""
        g = self.gate_states(t)
        v_ab = np.where(g["S1"] & g["S4"], 1.0, np.where(g["S2"] & g["S3"], -1.0, 0.0))
        v_cd = np.where(g["S5"] & g["S8"], 1.0, np.where(g["S6"] & g["S7"], -1.0, 0.0))
        return {"v_ab": v_ab, "v_cd": v_cd}

    # ---- description --------------------------------------------------------
    def describe(self) -> dict:
        return {
            **self.cfg.describe(),
            "register": self.register.to_dict(), "enabled": self.enabled,
            "command_limited": self.limited, "slew_limited": self.slew_limited,
            "switch_roles": {s: {"leg": LEG_OF[s], "side": "high" if s in HIGH_SIDE else "low",
                                 "bridge": "primary" if s in PRIMARY else "secondary",
                                 "pattern": "positive half-cycle" if s in POSITIVE_PATTERN else "negative half-cycle"} for s in SWITCHES},
        }
