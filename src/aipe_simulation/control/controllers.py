"""Discrete compensators and z-plane loop analysis for the DAB SPS control baseline.

Controllers
-----------
* :class:`DiscretePI` -- ``u[k] = Kp e[k] + x[k]``, ``x[k] = x[k-1] + Ki Ts e[k]``
  (backward-Euler integrator), output saturation with clamping anti-windup
  (the integrator is frozen while the output is saturated in the direction of
  the error) plus optional tracking anti-windup against downstream limiters:
  when the caller passes the value actually applied for the previous output
  (e.g. the modulator's rate-limited phase shift), the integrator is corrected
  by ``k_tracking (u_applied - u_prev)`` before the update. ``Ki`` is in
  physical units per second; the per-sample value ``Ki Ts`` is what a
  fixed-step firmware implementation stores.
* :class:`Df22Compensator` -- second-order direct form II transposed (DF22)
  ``y[n] = b0 e[n] + b1 e[n-1] + b2 e[n-2] - a1 y[n-1] - a2 y[n-2]`` with output
  clamping; the clamped value is written back into the output history so the
  recursive part cannot wind up. This is the structure TI's Digital Control
  Library calls DF22 (TI publishes the TIDA-010054 voltage-loop coefficients
  A1 = -1.8756666, A2 = 0.8756666, B0 = 1.4329852, B1 = -2.7994568,
  B2 = 1.3664965 for its own per-unit scaling and operating point; they are
  quoted in ``docs/dab-sps-control-spec.md`` as TI's values and are not used
  here).

Design rules
------------
* :func:`design_pi_for_static_plant` -- the cycle-averaged DAB output current
  responds to the phase shift within one period, so the current-loop plant is
  a static gain ``K = dI2/dphi`` plus delays. The PI is integrator-dominant:
  ``Kp`` is set from the admissible high-frequency loop gain (gain margin) and
  ``Ki`` is solved so that ``|L(e^{j w_c Ts})| = 1`` at the requested crossover.
* :func:`design_2p2z` -- continuous prototype
  ``C(s) = K (1 + s/w_z)^2 / (s (1 + s/w_p))`` whose coincident zeros are placed
  from the phase-margin target against the measured phase of the rest of the
  loop at the crossover, discretised with Tustin's rule pre-warped at the
  crossover (:func:`tustin_2p2z`) and scaled for unity loop gain at ``f_c``.

Loop analysis
-------------
:func:`stability_margins` evaluates a :class:`~.ztf.ZTransfer` loop gain on
the unit circle, reports every gain crossover (the model-boundaries guidance
of ``pe-python-control-analysis`` asks for all crossings), the phase margin at
the lowest crossover, the gain margin at the phase crossover and the
closed-loop pole radius. Pure delays (computation delay, one-period averaging
of the current measurement) enter as ``z^-n`` factors.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

from .ztf import ZTransfer


# ---------------------------------------------------------------------------- PI

@dataclass
class DiscretePI:
    kp: float  # output units per error unit
    ki: float  # output units per (error unit * s)
    ts: float  # s
    u_min: float = -math.inf
    u_max: float = math.inf
    k_tracking: float = 1.0  # tracking anti-windup gain against downstream limiters (0 disables)
    integrator: float = 0.0
    u_prev: float = 0.0
    saturated: bool = False

    def __post_init__(self) -> None:
        if self.ts <= 0 or not math.isfinite(self.ts):
            raise ValueError("ts must be positive")
        if self.u_min >= self.u_max:
            raise ValueError("u_min must be smaller than u_max")
        if self.kp < 0 or self.ki < 0:
            raise ValueError("kp and ki must be non-negative (use the error sign for the loop polarity)")
        if not 0 <= self.k_tracking <= 1:
            raise ValueError("k_tracking must lie in [0, 1]")

    @property
    def ki_per_sample(self) -> float:
        return self.ki * self.ts

    def reset(self, u0: float = 0.0, error: float = 0.0) -> None:
        """Bumpless initialisation: the next output for ``error`` equals ``u0``."""
        self.integrator = u0 - self.kp * error
        self.u_prev = u0
        self.saturated = False

    def step(self, error: float, u_applied: Optional[float] = None) -> float:
        """One update. ``u_applied`` is the value a downstream limiter actually applied for the previous output."""
        if u_applied is not None and self.k_tracking:
            self.integrator += self.k_tracking * (u_applied - self.u_prev)
        candidate = self.integrator + self.ki_per_sample * error
        u_unsat = self.kp * error + candidate
        u = min(max(u_unsat, self.u_min), self.u_max)
        self.saturated = u != u_unsat
        # clamping anti-windup: do not integrate further into the saturation
        if not self.saturated or (error * u_unsat) < 0:
            self.integrator = candidate
        self.u_prev = u
        return u

    def transfer_function(self) -> ZTransfer:
        """Linear part ``Kp + Ki Ts / (1 - z^-1)``."""
        return ZTransfer([self.kp + self.ki_per_sample, -self.kp], [1.0, -1.0])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ki_per_sample"] = self.ki_per_sample
        d["structure"] = ("u[k] = Kp e[k] + x[k]; x[k] = x[k-1] + Ki Ts e[k] + k_tracking (u_applied[k-1] - u[k-1]); "
                          "clamp to [u_min, u_max] with clamping anti-windup")
        return d


# -------------------------------------------------------------------------- DF22

@dataclass
class Df22Compensator:
    b0: float
    b1: float
    b2: float
    a1: float
    a2: float
    y_min: float = -math.inf
    y_max: float = math.inf
    e1: float = 0.0
    e2: float = 0.0
    y1: float = 0.0
    y2: float = 0.0
    saturated: bool = False

    def reset(self, y0: float = 0.0, error: float = 0.0) -> None:
        """Bumpless initialisation with a constant error history and output ``y0``."""
        self.e1 = self.e2 = error
        self.y1 = self.y2 = y0
        self.saturated = False

    def step(self, error: float) -> float:
        y = self.b0 * error + self.b1 * self.e1 + self.b2 * self.e2 - self.a1 * self.y1 - self.a2 * self.y2
        y_sat = min(max(y, self.y_min), self.y_max)
        self.saturated = y_sat != y
        self.e2, self.e1 = self.e1, error
        self.y2, self.y1 = self.y1, y_sat  # clamped value stored: no wind-up of the recursive part
        return y_sat

    def transfer_function(self) -> ZTransfer:
        return ZTransfer([self.b0, self.b1, self.b2], [1.0, self.a1, self.a2])

    def to_dict(self) -> dict:
        tf = self.transfer_function()
        return {"b0": self.b0, "b1": self.b1, "b2": self.b2, "a1": self.a1, "a2": self.a2,
                "y_min": self.y_min, "y_max": self.y_max,
                "difference_equation": "y[n] = b0 e[n] + b1 e[n-1] + b2 e[n-2] - a1 y[n-1] - a2 y[n-2]",
                "poles_z": [complex(p).real if abs(complex(p).imag) < 1e-12 else str(complex(p)) for p in tf.poles()],
                "zeros_z": [complex(z).real if abs(complex(z).imag) < 1e-12 else str(complex(z)) for z in tf.zeros()]}


def tustin_2p2z(k: float, f_z1: float, f_z2: float, f_p: float, ts: float, prewarp_hz: Optional[float] = None) -> tuple[list[float], list[float]]:
    """Tustin discretisation of ``C(s) = k (1 + s/w_z1)(1 + s/w_z2) / (s (1 + s/w_p))``.

    Returns ``([b0, b1, b2], [1, a1, a2])`` for the DF22 difference equation.
    With ``s = c (1 - z^-1) / (1 + z^-1)`` every first-order factor
    ``(1 + s/w)`` becomes ``[(1 + c/w) + (1 - c/w) z^-1] / (1 + z^-1)`` and the
    integrator ``s`` becomes ``c (1 - z^-1) / (1 + z^-1)``; the ``(1 + z^-1)``
    factors cancel between numerator and denominator.
    """
    for name, value in (("k", k), ("f_z1", f_z1), ("f_z2", f_z2), ("f_p", f_p), ("ts", ts)):
        if not (math.isfinite(value) and value > 0):
            raise ValueError(f"{name} must be a finite positive number")
    if prewarp_hz is None:
        c = 2.0 / ts
    else:
        w = 2 * math.pi * prewarp_hz
        if w * ts >= math.pi:
            raise ValueError("pre-warp frequency must be below the Nyquist frequency")
        c = w / math.tan(w * ts / 2)
    wz1, wz2, wp = (2 * math.pi * f for f in (f_z1, f_z2, f_p))
    num = np.convolve([1 + c / wz1, 1 - c / wz1], [1 + c / wz2, 1 - c / wz2]) * k
    den = np.convolve([1.0, -1.0], [1 + c / wp, 1 - c / wp]) * c
    b = (num / den[0]).tolist()
    a = (den / den[0]).tolist()
    return [float(v) for v in b], [float(v) for v in a]


# ------------------------------------------------------------------- loop analysis

def delay_phase_deg(f_hz: float, samples: float, ts: float) -> float:
    """Phase lag (degrees, positive number) of ``samples`` sampling periods at ``f_hz``."""
    return 360.0 * f_hz * samples * ts


def frequency_response(tf: ZTransfer, f_hz, ts: float) -> np.ndarray:
    return tf.freqresp(f_hz, ts)


def _unwrapped_phase_deg(h: np.ndarray) -> np.ndarray:
    phase = np.degrees(np.unwrap(np.angle(h)))
    # Anchor: a loop gain with integral action has non-positive phase at low frequency.
    if phase[0] > 0:
        phase -= 360.0
    return phase


def stability_margins(loop: ZTransfer, ts: float, f_min: float = 1.0, f_max: Optional[float] = None, n: int = 6000) -> dict:
    """Gain/phase margins of the open-loop gain ``loop`` evaluated on the unit circle.

    Returns the lowest gain crossover (``gain_crossover_hz``) with its phase
    margin, every gain crossover, the most restrictive gain margin at the phase
    crossovers (phase = -180 deg - k 360 deg) and the closed-loop stability
    verdict from the poles of ``loop / (1 + loop)``.
    """
    if ts <= 0:
        raise ValueError("ts must be positive")
    nyquist = 0.5 / ts
    f_max = min(f_max or nyquist, nyquist)
    if not (0 < f_min < f_max):
        raise ValueError("need 0 < f_min < f_max <= Nyquist")
    f = np.logspace(math.log10(f_min), math.log10(f_max), n)
    h = loop.freqresp(f, ts)
    mag = np.abs(h)
    phase = _unwrapped_phase_deg(h)
    log_mag = np.log10(np.maximum(mag, 1e-300))
    crossovers = []
    for i in np.where(np.diff(np.sign(log_mag)) != 0)[0]:
        x0, x1 = math.log10(f[i]), math.log10(f[i + 1])
        y0, y1 = log_mag[i], log_mag[i + 1]
        x = x0 if y1 == y0 else x0 + (0.0 - y0) * (x1 - x0) / (y1 - y0)
        fc = float(10 ** x)
        ph = float(np.interp(x, [x0, x1], [phase[i], phase[i + 1]]))
        pm = float(((ph + 180.0 + 180.0) % 360.0) - 180.0)
        crossovers.append({"f_hz": fc, "phase_deg": ph, "phase_margin_deg": pm,
                           "direction": "down" if y1 < y0 else "up"})
    gain_margins = []
    for target in (-180.0, -540.0):
        idx = np.where(np.diff(np.sign(phase - target)) != 0)[0]
        for i in idx:
            x0, x1 = math.log10(f[i]), math.log10(f[i + 1])
            p0, p1 = phase[i] - target, phase[i + 1] - target
            x = x0 if p1 == p0 else x0 + (0.0 - p0) * (x1 - x0) / (p1 - p0)
            m = float(np.interp(x, [x0, x1], [log_mag[i], log_mag[i + 1]]))
            gain_margins.append({"f_hz": float(10 ** x), "gain_margin_db": -20.0 * m})
        if idx.size == 0 and abs(phase[-1] - target) <= 1e-6:
            # the phase reaches the target exactly at the last grid point (e.g. an integrator with one delay at Nyquist)
            gain_margins.append({"f_hz": float(f[-1]), "gain_margin_db": float(-20.0 * log_mag[-1])})
    closed = loop.feedback()
    first = crossovers[0] if crossovers else None
    gm = min(gain_margins, key=lambda g: g["gain_margin_db"]) if gain_margins else None
    return {
        "gain_crossover_hz": first["f_hz"] if first else None,
        "phase_margin_deg": first["phase_margin_deg"] if first else None,
        "gain_margin_db": gm["gain_margin_db"] if gm else None,
        "phase_crossover_hz": gm["f_hz"] if gm else None,
        "all_gain_crossovers": crossovers,
        "all_phase_crossovers": gain_margins,
        "low_frequency_gain_db": float(20 * log_mag[0]),
        "closed_loop_max_pole_radius": closed.max_pole_radius(),
        "closed_loop_stable": closed.is_stable(),
        "frequency_range_hz": [float(f[0]), float(f[-1])], "samples": n, "ts_s": ts,
    }


# --------------------------------------------------------------------- design rules

def design_pi_for_static_plant(k_plant: float, f_c: float, ts: float, delay_samples: int = 2,
                               high_frequency_gain: float = 0.25, u_min: float = -math.inf, u_max: float = math.inf) -> dict:
    """PI for a static plant gain ``k_plant`` with ``delay_samples`` pure delays in the loop.

    ``high_frequency_gain`` is the loop gain ``k_plant Kp`` left at high
    frequency (0.25 corresponds to about 12 dB of gain margin before the
    integral term adds its share at the Nyquist frequency). ``Ki`` solves
    ``|k_plant (Kp + Ki Ts /(1 - z^-1))| = 1`` at ``z = e^{j 2 pi f_c Ts}``.
    """
    for name, value in (("k_plant", k_plant), ("f_c", f_c), ("ts", ts)):
        if not (math.isfinite(value) and value > 0):
            raise ValueError(f"{name} must be a finite positive number")
    if not 0 <= high_frequency_gain < 1:
        raise ValueError("high_frequency_gain must lie in [0, 1)")
    if f_c >= 0.5 / ts:
        raise ValueError("crossover must be below the Nyquist frequency")
    kp = high_frequency_gain / k_plant
    z = np.exp(1j * 2 * math.pi * f_c * ts)
    w = 1.0 / (1.0 - 1.0 / z)  # integrator response at the crossover
    # |kp + x w|^2 = 1/k^2 with x = Ki Ts  ->  |w|^2 x^2 + 2 kp Re(w) x + kp^2 - 1/k^2 = 0
    aa, bb, cc = abs(w) ** 2, 2 * kp * w.real, kp ** 2 - 1.0 / k_plant ** 2
    disc = bb * bb - 4 * aa * cc
    if disc < 0:
        raise ValueError("no positive integral gain reaches the requested crossover with this proportional gain")
    x = float((-bb + math.sqrt(disc)) / (2 * aa))
    if x <= 0:
        raise ValueError("the proportional gain alone already exceeds unity loop gain at the crossover")
    ki = x / ts
    pi = DiscretePI(kp=kp, ki=ki, ts=ts, u_min=u_min, u_max=u_max)
    loop = pi.transfer_function() * ZTransfer.gain(k_plant) * ZTransfer.delay(delay_samples)
    margins = stability_margins(loop, ts)
    return {"pi": pi, "kp": kp, "ki": ki, "ki_per_sample": ki * ts, "k_plant": k_plant, "f_c_target_hz": f_c,
            "delay_samples": delay_samples, "high_frequency_gain": high_frequency_gain, "loop": loop, "margins": margins}


def design_2p2z(loop_rest: ZTransfer, ts: float, f_c: float, pm_target_deg: float = 60.0, f_pole: Optional[float] = None,
                f_zero: Optional[float] = None, y_min: float = -math.inf, y_max: float = math.inf) -> dict:
    """2P2Z (DF22) design against ``loop_rest`` (everything in the loop except the compensator).

    The continuous prototype is ``C(s) = K (1 + s/w_z)^2 / (s (1 + s/w_p))``.
    Unless ``f_zero`` is given, the coincident zeros are placed so that the
    prototype contributes the phase needed for ``pm_target_deg`` at ``f_c``::

        2 atan(f_c/f_z) = pm_target - 180 - phase_rest(f_c) + 90 + atan(f_c/f_p)

    The high-frequency pole defaults to ``f_s / 20`` (a tenth of the Nyquist
    frequency) to roll off switching-frequency content without hurting the
    crossover. Tustin with pre-warping at ``f_c`` keeps the designed
    crossover; ``K`` is then scaled for unity loop gain at ``f_c`` and the
    final margins are evaluated on the discrete loop.
    """
    if not (math.isfinite(f_c) and 0 < f_c < 0.5 / ts):
        raise ValueError("f_c must lie between 0 and the Nyquist frequency")
    f_pole = f_pole or 1.0 / (20 * ts)
    f_grid = np.logspace(math.log10(max(f_c / 1000, 0.1)), math.log10(f_c), 400)
    phase_rest = float(_unwrapped_phase_deg(loop_rest.freqresp(f_grid, ts))[-1])
    pole_lag = math.degrees(math.atan(f_c / f_pole))
    if f_zero is None:
        required = pm_target_deg - 180.0 - phase_rest  # phase the prototype must contribute at f_c
        theta = (required + 90.0 + pole_lag) / 2.0  # = atan(f_c / f_z)
        if not 0.0 < theta < 90.0:
            raise ValueError(f"phase-margin target {pm_target_deg} deg infeasible: the compensator would need {required:.1f} deg "
                             f"at {f_c:g} Hz (rest of loop: {phase_rest:.1f} deg)")
        f_zero = f_c / math.tan(math.radians(theta))
    b, a = tustin_2p2z(1.0, f_zero, f_zero, f_pole, ts, prewarp_hz=f_c)
    unity = ZTransfer(b, a)
    gain_at_fc = abs(complex((unity * loop_rest).freqresp(f_c, ts)))
    k = 1.0 / gain_at_fc
    comp = Df22Compensator(*(k * v for v in b), a[1], a[2], y_min=y_min, y_max=y_max)
    loop = comp.transfer_function() * loop_rest
    margins = stability_margins(loop, ts)
    return {"compensator": comp, "coefficients": {"b0": comp.b0, "b1": comp.b1, "b2": comp.b2, "a1": comp.a1, "a2": comp.a2},
            "prototype": {"k_integrator": k, "f_zero_hz": f_zero, "f_zero2_hz": f_zero, "f_pole_hz": f_pole,
                          "form": "C(s) = K (1 + s/w_z)^2 / (s (1 + s/w_p)); Tustin pre-warped at f_c"},
            "phase_rest_at_fc_deg": phase_rest, "pm_target_deg": pm_target_deg, "f_c_target_hz": f_c, "loop": loop, "margins": margins}


@dataclass
class LoopSummary:
    """JSON-friendly margin summary with the design targets."""

    name: str
    f_c_target_hz: float
    margins: dict
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        m = self.margins
        return {"name": self.name, "f_c_target_hz": self.f_c_target_hz, "gain_crossover_hz": m.get("gain_crossover_hz"),
                "phase_margin_deg": m.get("phase_margin_deg"), "gain_margin_db": m.get("gain_margin_db"),
                "phase_crossover_hz": m.get("phase_crossover_hz"), "closed_loop_stable": m.get("closed_loop_stable"),
                "closed_loop_max_pole_radius": m.get("closed_loop_max_pole_radius"),
                "n_gain_crossovers": len(m.get("all_gain_crossovers", [])), "notes": self.notes}
