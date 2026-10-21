"""Engineering metrics on non-uniformly sampled waveforms.

All integrals use the trapezoidal rule on the solver's own time grid (no
resampling), so the metric error is governed by the solver step. Interval
and crossing functions use linear interpolation between samples.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def _check(t: np.ndarray, x: np.ndarray) -> None:
    if t.shape != x.shape or t.ndim != 1 or t.size < 2:
        raise ValueError("time and signal must be 1-D arrays of equal length >= 2")


def integrate(t: np.ndarray, x: np.ndarray) -> float:
    """Trapezoidal integral of x over the full time span."""
    _check(t, x)
    return float(np.sum(0.5 * (x[1:] + x[:-1]) * np.diff(t)))


def average(t: np.ndarray, x: np.ndarray) -> float:
    _check(t, x)
    span = t[-1] - t[0]
    if span <= 0:
        raise ValueError("time span must be positive")
    return integrate(t, x) / span


def rms(t: np.ndarray, x: np.ndarray) -> float:
    return float(np.sqrt(average(t, x * x)))


def peak(t: np.ndarray, x: np.ndarray) -> dict:
    _check(t, x)
    imax, imin = int(np.argmax(x)), int(np.argmin(x))
    return {"max": float(x[imax]), "t_max": float(t[imax]), "min": float(x[imin]), "t_min": float(t[imin]),
            "abs_max": float(max(abs(x[imax]), abs(x[imin])))}


def ripple(t: np.ndarray, x: np.ndarray) -> dict:
    p = peak(t, x)
    mean = average(t, x)
    return {"peak_to_peak": p["max"] - p["min"], "mean": mean,
            "relative_peak_to_peak": (p["max"] - p["min"]) / abs(mean) if mean else float("inf")}


def average_power(t: np.ndarray, v: np.ndarray, i: np.ndarray) -> float:
    return average(t, v * i)


def interp_at(t: np.ndarray, x: np.ndarray, times, side: str = "exact") -> np.ndarray:
    """Linear interpolation of x at ``times``.

    ``side='before'`` evaluates just before each time (the limit from the left,
    useful for the current at a switching instant on a discontinuous waveform)
    by stepping back one half of the local time step; ``'after'`` steps forward.
    """
    _check(t, x)
    times = np.atleast_1d(np.asarray(times, dtype=np.float64))
    if side != "exact":
        idx = np.clip(np.searchsorted(t, times), 1, t.size - 1)
        local = np.diff(t)[np.clip(idx - 1, 0, t.size - 2)]
        times = times - 0.5 * local if side == "before" else times + 0.5 * local
    return np.interp(times, t, x)


def threshold_crossings(t: np.ndarray, x: np.ndarray, level: float, direction: str = "both") -> np.ndarray:
    """Times at which x crosses ``level`` (linear interpolation).

    ``direction``: ``'rising'``, ``'falling'`` or ``'both'``.
    """
    _check(t, x)
    above = x > level
    change = np.where(above[1:] != above[:-1])[0]
    times = []
    for k in change:
        x0, x1 = x[k], x[k + 1]
        if x1 == x0:
            continue
        rising = x1 > x0
        if direction == "rising" and not rising:
            continue
        if direction == "falling" and rising:
            continue
        times.append(t[k] + (level - x0) * (t[k + 1] - t[k]) / (x1 - x0))
    return np.array(times)


def conduction_intervals(t: np.ndarray, i: np.ndarray, threshold: float) -> list[dict]:
    """Intervals where |i| exceeds ``threshold``, with duration, charge and mean current."""
    _check(t, i)
    mask = np.abs(i) > threshold
    intervals = []
    k = 0
    n = t.size
    while k < n:
        if not mask[k]:
            k += 1
            continue
        start = k
        while k < n and mask[k]:
            k += 1
        end = k - 1
        if end > start:
            seg_t, seg_i = t[start:end + 1], i[start:end + 1]
            charge = integrate(seg_t, seg_i)
            duration = float(seg_t[-1] - seg_t[0])
            intervals.append({"t_start": float(seg_t[0]), "t_end": float(seg_t[-1]), "duration": duration,
                              "charge": charge, "mean_current": charge / duration if duration > 0 else 0.0,
                              "rms_current": rms(seg_t, seg_i), "peak_abs": float(np.max(np.abs(seg_i)))})
    return intervals


def volt_seconds(t: np.ndarray, v: np.ndarray, t0: float, period: float) -> dict:
    """Volt-second balance and flux-linkage swing of a voltage over the cycle starting at t0."""
    mask = (t >= t0 - 1e-15) & (t <= t0 + period + 1e-15)
    tt, vv = t[mask], v[mask]
    if tt.size < 2:
        raise ValueError("cycle window contains fewer than two samples")
    lam = np.concatenate([[0.0], np.cumsum(0.5 * (vv[1:] + vv[:-1]) * np.diff(tt))])
    return {"net_volt_seconds": float(lam[-1]), "flux_linkage_peak_to_peak": float(lam.max() - lam.min()),
            "positive_volt_seconds": float(integrate(tt, np.clip(vv, 0, None))),
            "relative_imbalance": float(abs(lam[-1]) / (lam.max() - lam.min())) if lam.max() > lam.min() else 0.0}


def periodicity_error(t: np.ndarray, x: np.ndarray, period: float, t0: Optional[float] = None) -> float:
    """max |x(t + T) - x(t)| / max |x| over the overlap of the window with its shift."""
    _check(t, x)
    t0 = t[0] if t0 is None else t0
    t1 = t[-1] - period
    if t1 <= t0:
        raise ValueError("window shorter than one period")
    grid = np.linspace(t0, t1, 2001)
    a = np.interp(grid, t, x)
    b = np.interp(grid + period, t, x)
    scale = float(np.max(np.abs(x))) or 1.0
    return float(np.max(np.abs(a - b)) / scale)


def half_wave_symmetry_error(t: np.ndarray, x: np.ndarray, period: float, t0: Optional[float] = None) -> float:
    """max |x(t + T/2) + x(t)| / max |x| (zero for an ideal half-wave antisymmetric waveform)."""
    _check(t, x)
    t0 = t[0] if t0 is None else t0
    t1 = t[-1] - period / 2
    if t1 <= t0:
        raise ValueError("window shorter than half a period")
    grid = np.linspace(t0, t1, 2001)
    a = np.interp(grid, t, x)
    b = np.interp(grid + period / 2, t, x)
    scale = float(np.max(np.abs(x))) or 1.0
    return float(np.max(np.abs(a + b)) / scale)


def cycle_values(t: np.ndarray, x: np.ndarray, t_origin: float, period: float, fn=rms) -> list[dict]:
    """Apply ``fn(t, x)`` to each complete cycle [t_origin + kT, t_origin + (k+1)T] inside the data."""
    _check(t, x)
    k0 = int(np.ceil((t[0] - t_origin) / period))
    k1 = int(np.floor((t[-1] - t_origin) / period)) - 1
    out = []
    for k in range(k0, k1 + 1):
        a, b = t_origin + k * period, t_origin + (k + 1) * period
        mask = (t > a) & (t < b)
        if np.count_nonzero(mask) >= 2:
            # Include interpolated samples exactly at the cycle boundaries so every cycle spans one full period.
            tt = np.concatenate([[a], t[mask], [b]])
            xx = np.concatenate([[np.interp(a, t, x)], x[mask], [np.interp(b, t, x)]])
            out.append({"cycle": k, "t_start": a, "t_end": b, "value": float(fn(tt, xx))})
    return out
