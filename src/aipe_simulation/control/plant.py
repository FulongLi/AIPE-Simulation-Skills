"""Cycle-averaged sampled-data model of the DAB output port for control design.

Model assumptions (stated once here, repeated in every result):

* **Lossless SPS power stage**: ideal switches, ideal transformer, no dead-time
  effect on the transferred power, no magnetising current, stiff port-1 source
  (optionally behind a static series resistance).
* **Cycle-averaged**: within one update interval the phase shift and the port
  voltages are held constant and the transferred power is the lossless
  single-phase-shift law. The series-inductor current settles within one
  switching period and is not a state of this model; the model is therefore
  only meaningful for control bandwidths well below ``f_sw / 10``.
* **Output port**: the DC-link capacitor ``C2`` integrates the difference
  between the cycle-averaged converter current and the load current. The load
  is a resistor and/or a current source (positive = drawn from port 2,
  negative = injected, i.e. reverse power flow). The capacitor update is the
  exact zero-order-hold discretisation for piecewise-constant currents.

Closed forms (De Doncker, Divan, Kheraluwala, IEEE Trans. Ind. Appl. 27(1),
1991), re-derived here from the AIPE-Design-Agent analytic model
``pea/converters/dab_sps.py`` so that this package has no import dependency on
the sibling repository (the test-suite cross-checks both when it is present)::

    V2' = n V2,  g(phi) = phi (pi - |phi|),  |phi| <= pi/2
    P(phi)  = V1 V2' g(phi) / (2 pi^2 f_sw L)          W, positive port 1 -> port 2
    I2(phi) = P / V2 = n V1 g(phi) / (2 pi^2 f_sw L)   A, independent of V2
    I1(phi) = P / V1 = n V2 g(phi) / (2 pi^2 f_sw L)   A
    dI2/dphi = n V1 (pi - 2 |phi|) / (2 pi^2 f_sw L)   A/rad (small-signal current gain)
    dP/dphi  = V2 dI2/dphi                             W/rad

Because ``I2`` does not depend on ``V2``, the SPS-controlled DAB behaves as a
phase-shift-controlled current source into the output capacitor; the voltage
dynamics are those of ``C2`` with the load.

Sign conventions follow :mod:`aipe_simulation.dab`: ``phi > 0`` means the
secondary bridge lags and power flows from port 1 to port 2; ``i_L`` flows
from node ``a`` towards the transformer; the series-current waveform origin
``"centre"`` is the centre of the primary positive half-cycle.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

from .ztf import ZTransfer

Origin = str  # "rising_edge" | "centre"


# --------------------------------------------------------------------------- closed forms

def _check_positive(**values: float) -> None:
    for name, value in values.items():
        if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
            raise ValueError(f"{name} must be a finite positive number")


def _check_phi(phi_rad: float) -> None:
    if not (math.isfinite(phi_rad) and -math.pi / 2 <= phi_rad <= math.pi / 2):
        raise ValueError("phi_rad must lie within [-pi/2, pi/2]")


def sps_g(phi_rad: float) -> float:
    """Dimensionless SPS power function ``phi (pi - |phi|)`` (odd in phi)."""
    _check_phi(phi_rad)
    return phi_rad * (math.pi - abs(phi_rad))


def sps_power(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float) -> float:
    """Transferred power in W (positive from port 1 to port 2)."""
    _check_positive(v1=v1, n_ratio=n_ratio, f_sw=f_sw, l_total=l_total)
    if v2 < 0:
        raise ValueError("v2 must be non-negative")
    return v1 * n_ratio * v2 * sps_g(phi_rad) / (2 * math.pi ** 2 * f_sw * l_total)


def sps_output_current(v1: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float) -> float:
    """Cycle-averaged port-2 DC current in A (independent of V2)."""
    _check_positive(v1=v1, n_ratio=n_ratio, f_sw=f_sw, l_total=l_total)
    return n_ratio * v1 * sps_g(phi_rad) / (2 * math.pi ** 2 * f_sw * l_total)


def sps_max_power(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float) -> float:
    """Maximum SPS power (|phi| = pi/2)."""
    return v1 * n_ratio * v2 / (8 * f_sw * l_total)


def output_current_gain(v1: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float) -> float:
    """Small-signal gain dI2/dphi in A/rad at the operating point ``phi_rad``."""
    _check_positive(v1=v1, n_ratio=n_ratio, f_sw=f_sw, l_total=l_total)
    _check_phi(phi_rad)
    return n_ratio * v1 * (math.pi - 2 * abs(phi_rad)) / (2 * math.pi ** 2 * f_sw * l_total)


def power_gain(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float) -> float:
    """Small-signal gain dP/dphi in W/rad at the operating point."""
    return v2 * output_current_gain(v1, n_ratio, f_sw, l_total, phi_rad)


def phase_shift_for_output_current(v1: float, n_ratio: float, f_sw: float, l_total: float, i2: float) -> float:
    """Signed phase shift (rad, |phi| <= pi/2) that delivers the port-2 current ``i2`` (smaller root)."""
    _check_positive(v1=v1, n_ratio=n_ratio, f_sw=f_sw, l_total=l_total)
    i_max = n_ratio * v1 / (8 * f_sw * l_total)
    if abs(i2) > i_max * (1 + 1e-12):
        raise ValueError(f"requested current {i2:.6g} A exceeds the SPS maximum {i_max:.6g} A")
    c = 2 * math.pi ** 2 * f_sw * l_total * abs(i2) / (n_ratio * v1)
    phi = (math.pi - math.sqrt(max(math.pi ** 2 - 4 * c, 0.0))) / 2
    return math.copysign(phi, i2) if i2 != 0 else 0.0


def phase_shift_for_power(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, p: float) -> float:
    """Signed phase shift delivering power ``p`` (W) at the port voltages."""
    _check_positive(v2=v2)
    return phase_shift_for_output_current(v1, n_ratio, f_sw, l_total, p / v2)


# ------------------------------------------------------------ series current (lossless)

def series_current_breakpoints(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float,
                               origin: Origin = "rising_edge") -> list[tuple[float, float]]:
    """Exact piecewise-linear lossless series current over one period.

    Re-derivation of ``dab_sps.breakpoints``: the inductor voltage is
    ``v_ab - n v_cd`` in each sub-interval of the first half period and the
    waveform is half-wave antisymmetric, ``i(t + T/2) = -i(t)``. With
    ``origin="rising_edge"`` ``t = 0`` is the -V1 -> +V1 transition of
    ``v_ab``; with ``origin="centre"`` it is the centre of the positive
    half-cycle (the AIPE gating convention), i.e. the points are shifted by
    ``-T/4`` and re-wrapped into ``[0, T]``.
    """
    _check_positive(v1=v1, n_ratio=n_ratio, f_sw=f_sw, l_total=l_total)
    _check_phi(phi_rad)
    if v2 < 0:
        raise ValueError("v2 must be non-negative")
    T = 1.0 / f_sw
    half = T / 2
    v2r = n_ratio * v2
    t_phi = phi_rad / (2 * math.pi) * T
    inner = t_phi % half
    bounds = sorted({0.0, inner, half})
    seg = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        if hi - lo <= 0:
            continue
        mid = (lo + hi) / 2
        v_ab = v1 if (mid % T) < half else -v1
        v_cd = v2r if ((mid - t_phi) % T) < half else -v2r
        seg.append((lo, hi, (v_ab - v_cd) / l_total))
    delta_half = sum(slope * (hi - lo) for lo, hi, slope in seg)
    current = -delta_half / 2
    points = [(0.0, current)]
    for lo, hi, slope in seg:
        current += slope * (hi - lo)
        points.append((hi, current))
    for lo, hi, slope in seg:
        current -= slope * (hi - lo)
        points.append((hi + half, current))
    if origin == "rising_edge":
        return points
    if origin != "centre":
        raise ValueError("origin must be 'rising_edge' or 'centre'")
    # Shift the origin to the centre of the positive half-cycle: t_c = t - T/4.
    def value_at(tau: float) -> float:
        return _interp(points, tau % T)
    knots = sorted({(t - T / 4) % T for t, _ in points} | {0.0, T})
    return [(t, value_at(t + T / 4)) for t in knots]


def _interp(points: list[tuple[float, float]], tau: float) -> float:
    for (t0, i0), (t1, i1) in zip(points[:-1], points[1:]):
        if t0 - 1e-18 <= tau <= t1 + 1e-18:
            return i1 if t1 == t0 else i0 + (i1 - i0) * (tau - t0) / (t1 - t0)
    return points[-1][1]


def series_current_at(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float, t: float,
                      origin: Origin = "centre") -> float:
    """Lossless series inductor current at time ``t`` (periodic extension)."""
    T = 1.0 / f_sw
    pts = series_current_breakpoints(v1, v2, n_ratio, f_sw, l_total, phi_rad, origin)
    return _interp(pts, t % T)


def series_current_peak(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float) -> float:
    """Peak |i_L| of the lossless waveform (A, primary referred)."""
    pts = series_current_breakpoints(v1, v2, n_ratio, f_sw, l_total, phi_rad)
    return max(abs(i) for _, i in pts)


def series_current_rms(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float) -> float:
    """RMS of the lossless piecewise-linear series current (A, primary referred)."""
    pts = series_current_breakpoints(v1, v2, n_ratio, f_sw, l_total, phi_rad)
    acc = 0.0
    for (t0, i0), (t1, i1) in zip(pts[:-1], pts[1:]):
        acc += (i0 * i0 + i0 * i1 + i1 * i1) / 3 * (t1 - t0)
    return math.sqrt(acc * f_sw)


# ------------------------------------------------------------------------- plant model

@dataclass
class DabSpsPlantParameters:
    """Cycle-averaged plant parameters (SI units)."""

    v1: float = 800.0  # V, port-1 source voltage
    n_ratio: float = 2.0  # N_p / N_s
    f_sw: float = 100e3  # Hz
    l_total: float = 35e-6  # H, primary-referred series inductance
    c2: float = 400e-6  # F, port-2 DC-link capacitance (AIPE assumption; TI TIDA-010054 uses 60 uF film)
    r_load: Optional[float] = 16.0  # Ohm, resistive load (None = no resistor)
    i_load: float = 0.0  # A, current-source load; positive drawn from port 2, negative injected (reverse power)
    r_source: float = 0.0  # Ohm, static port-1 source resistance (0 = stiff source)
    ts: float = 10e-6  # s, update interval of the sampled-data model (one switching period by default)

    def validate(self) -> list[str]:
        problems = []
        for name in ("v1", "n_ratio", "f_sw", "l_total", "c2", "ts"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value > 0):
                problems.append(f"{name} must be a finite positive number")
        if self.r_load is not None and not (math.isfinite(self.r_load) and self.r_load > 0):
            problems.append("r_load must be None or a finite positive resistance")
        if self.r_source < 0 or not math.isfinite(self.r_source):
            problems.append("r_source must be non-negative")
        if not math.isfinite(self.i_load):
            problems.append("i_load must be finite")
        if self.ts > 0 and self.f_sw > 0 and self.ts < 1.0 / self.f_sw * (1 - 1e-9):
            problems.append("ts must be at least one switching period: the model is cycle-averaged")
        return problems

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def period(self) -> float:
        return 1.0 / self.f_sw

    @property
    def i2_max(self) -> float:
        """Port-2 current at |phi| = pi/2."""
        return self.n_ratio * self.v1 / (8 * self.f_sw * self.l_total)

    @property
    def model_assumptions(self) -> list[str]:
        return list(MODEL_ASSUMPTIONS)


MODEL_ASSUMPTIONS = (
    "Lossless SPS power stage: ideal switches, ideal transformer, no dead-time effect on power, stiff port-1 source (optional static series resistance).",
    "Cycle-averaged: phase shift and port voltages held over one update interval; the series-inductor current is not a state (valid for bandwidths well below f_sw/10).",
    "Magnetising current neglected; the lossless piecewise-linear series current is reported as a quasi-static estimate for protection studies only.",
    "Port-2 capacitor update is the exact ZOH discretisation of C2 with a resistive and/or current-source load for piecewise-constant currents.",
    "No sensor dynamics, ADC quantisation or noise; the one-period averaging of the measured current and the computation delay are modelled in the controller loop.",
)


class DabSpsPlant:
    """Sampled-data plant: ``step(phi)`` advances the port-2 voltage by one update interval."""

    def __init__(self, params: Optional[DabSpsPlantParameters] = None, v2_initial: float = 400.0):
        self.p = params or DabSpsPlantParameters()
        problems = self.p.validate()
        if problems:
            raise ValueError("invalid plant parameters: " + "; ".join(problems))
        self.reset(v2_initial)

    def reset(self, v2_initial: float = 400.0) -> None:
        if v2_initial < 0 or not math.isfinite(v2_initial):
            raise ValueError("initial port-2 voltage must be non-negative")
        self.v2 = float(v2_initial)
        self.i2 = 0.0  # A, converter current into port 2 over the last interval
        self.i1 = 0.0  # A, current drawn from port 1 over the last interval
        self.p2 = 0.0  # W, power into port 2 (= power from port 1, lossless)
        self.v1_bus = self.p.v1
        self.phi = 0.0
        self.enabled = False
        self.i_l_peak = 0.0  # A, quasi-static lossless series-current peak (primary referred)
        self.i_l_rms = 0.0
        self.i_load_total = 0.0
        self.t = 0.0

    # ---- load configuration -------------------------------------------------
    def set_load(self, r_load: Optional[float] = "keep", i_load: Optional[float] = None) -> None:
        if r_load != "keep":
            self.p.r_load = r_load
        if i_load is not None:
            self.p.i_load = float(i_load)
        problems = self.p.validate()
        if problems:
            raise ValueError("invalid plant parameters: " + "; ".join(problems))

    def load_current(self, v2: Optional[float] = None) -> float:
        v2 = self.v2 if v2 is None else v2
        resistive = v2 / self.p.r_load if self.p.r_load is not None else 0.0
        return resistive + self.p.i_load

    # ---- dynamics -----------------------------------------------------------
    def measurements(self) -> dict:
        """Quantities available to the controller at the current sample instant."""
        return {"t": self.t, "v2": self.v2, "i2": self.i2, "i1": self.i1, "p2": self.p2, "v1_bus": self.v1_bus,
                "i_l_peak": self.i_l_peak, "i_l_rms": self.i_l_rms, "i_load": self.i_load_total, "phi": self.phi,
                "enabled": self.enabled}

    def step(self, phi_rad: float, enabled: bool = True, dt: Optional[float] = None) -> dict:
        """Advance one interval with the applied phase shift; returns the measurements after the step."""
        p = self.p
        dt = p.ts if dt is None else dt
        if dt <= 0:
            raise ValueError("dt must be positive")
        _check_phi(phi_rad)
        v2_start = self.v2
        if enabled:
            g = sps_g(phi_rad)
            k = p.n_ratio / (2 * math.pi ** 2 * p.f_sw * p.l_total)
            i1 = k * v2_start * g  # independent of the bus voltage (lossless)
            v1_bus = p.v1 - p.r_source * i1
            if v1_bus <= 0:
                raise ValueError("port-1 source resistance collapses the bus voltage; model invalid")
            i2 = k * v1_bus * g
            self.i_l_peak = series_current_peak(v1_bus, v2_start, p.n_ratio, p.f_sw, p.l_total, phi_rad)
            self.i_l_rms = series_current_rms(v1_bus, v2_start, p.n_ratio, p.f_sw, p.l_total, phi_rad)
        else:
            i1 = i2 = 0.0
            v1_bus = p.v1
            self.i_l_peak = self.i_l_rms = 0.0
        i_src = p.i_load
        if p.r_load is not None:
            a = math.exp(-dt / (p.r_load * p.c2))
            v2_end = a * v2_start + p.r_load * (i2 - i_src) * (1 - a)
        else:
            v2_end = v2_start + (i2 - i_src) * dt / p.c2
        self.i_load_total = self.load_current(v2_start)
        self.v2 = max(v2_end, 0.0)  # the diode bridge cannot drive the port negative
        self.i2, self.i1, self.v1_bus, self.phi, self.enabled = i2, i1, v1_bus, phi_rad, enabled
        self.p2 = v2_start * i2
        self.t += dt
        return self.measurements()

    # ---- small-signal model -------------------------------------------------
    def current_gain(self, phi_rad: float) -> float:
        """dI2/dphi in A/rad at ``phi_rad`` (with the nominal bus voltage)."""
        return output_current_gain(self.p.v1, self.p.n_ratio, self.p.f_sw, self.p.l_total, phi_rad)

    def output_port_tf(self, r_load: Optional[float] = "keep") -> ZTransfer:
        """Exact ZOH discretisation from the interval current (A) to the sampled port-2 voltage (V).

        Resistive load: ``v[k+1] = a v[k] + R (1 - a) i[k]``, ``a = exp(-Ts / (R C2))``;
        current-source load only: ``v[k+1] = v[k] + i[k] Ts / C2``.
        """
        r = self.p.r_load if r_load == "keep" else r_load
        if r is None:
            return ZTransfer([0.0, self.p.ts / self.p.c2], [1.0, -1.0])
        a = math.exp(-self.p.ts / (r * self.p.c2))
        return ZTransfer([0.0, r * (1 - a)], [1.0, -a])

    def small_signal(self, phi_rad: float, v2: Optional[float] = None) -> dict:
        """Linearisation at an operating point (SI units)."""
        p = self.p
        v2 = self.v2 if v2 is None else v2
        k_i = self.current_gain(phi_rad)
        pole_hz = (1.0 / (2 * math.pi * p.r_load * p.c2)) if p.r_load is not None else 0.0
        return {
            "operating_point": {"phi_rad": phi_rad, "phi_deg": math.degrees(phi_rad), "v1_V": p.v1, "v2_V": v2,
                                "i2_A": sps_output_current(p.v1, p.n_ratio, p.f_sw, p.l_total, phi_rad),
                                "p_W": sps_power(p.v1, v2, p.n_ratio, p.f_sw, p.l_total, phi_rad)},
            "dI2_dphi_A_per_rad": k_i, "dI2_dphi_A_per_deg": k_i * math.pi / 180,
            "dP_dphi_W_per_rad": v2 * k_i, "dP_dphi_W_per_deg": v2 * k_i * math.pi / 180,
            "output_port_pole_Hz": pole_hz, "output_port_dc_gain_V_per_A": p.r_load if p.r_load is not None else float("inf"),
            "phi_to_v2_dc_gain_V_per_rad": (p.r_load * k_i) if p.r_load is not None else float("inf"),
            "output_port_tf_z": self.output_port_tf().to_dict(),
            "c2_F": p.c2, "r_load_Ohm": p.r_load, "ts_s": p.ts,
            "note": "I2 is independent of V2 in the lossless SPS law: the converter is a phase-shift-controlled current source into C2",
        }

    def describe(self) -> dict:
        return {"parameters": self.p.to_dict(), "assumptions": self.p.model_assumptions,
                "i2_max_A": self.p.i2_max, "p_max_W_at_v2": sps_max_power(self.p.v1, self.v2, self.p.n_ratio, self.p.f_sw, self.p.l_total)}
