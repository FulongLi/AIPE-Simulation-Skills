"""Periodic steady-state window identification.

A switching simulation is only usable for engineering metrics once the initial
transient has decayed. The detector computes a cycle-by-cycle metric (RMS by
default) of a reference signal, requires the relative cycle-to-cycle change to
stay below ``rel_tol`` for the final ``window_cycles`` cycles, and additionally
checks the periodicity error of the signal within the proposed window. The
returned window always covers whole switching periods aligned to ``t_origin``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

from .metrics import cycle_values, periodicity_error, rms


@dataclass
class SteadyStateResult:
    ok: bool
    reason: str
    t0: Optional[float] = None
    t1: Optional[float] = None
    cycles_in_window: int = 0
    cycles_available: int = 0
    converged_from_cycle: Optional[int] = None
    max_relative_change_in_window: Optional[float] = None
    periodicity_error: Optional[float] = None
    per_cycle_metric: list[dict] = field(default_factory=list)
    rel_tol: float = 1e-3
    periodicity_tol: float = 1e-2

    def to_dict(self) -> dict:
        return asdict(self)


def find_steady_state_window(t: np.ndarray, x: np.ndarray, period: float, t_origin: float = 0.0,
                             rel_tol: float = 1e-3, window_cycles: int = 4, periodicity_tol: float = 1e-2,
                             metric=rms) -> SteadyStateResult:
    per_cycle = cycle_values(t, x, t_origin, period, metric)
    n = len(per_cycle)
    if n < window_cycles + 1:
        return SteadyStateResult(False, f"only {n} complete cycles available; need at least {window_cycles + 1}",
                                 cycles_available=n, per_cycle_metric=per_cycle, rel_tol=rel_tol, periodicity_tol=periodicity_tol)
    values = np.array([c["value"] for c in per_cycle])
    scale = abs(values[-1]) if values[-1] != 0 else (np.max(np.abs(values)) or 1.0)
    rel_change = np.abs(np.diff(values)) / scale  # rel_change[k] between cycle k and k+1
    # Walk backwards to find the first cycle from which all subsequent changes are small.
    converged_from = n - 1
    while converged_from > 0 and rel_change[converged_from - 1] <= rel_tol:
        converged_from -= 1
    converged_cycles = n - converged_from
    if converged_cycles < window_cycles:
        return SteadyStateResult(False, f"cycle metric still changing: only {converged_cycles} converged cycles "
                                        f"(< {window_cycles}); last relative change {rel_change[-1]:.3e} > {rel_tol:g}",
                                 cycles_available=n, converged_from_cycle=per_cycle[converged_from]["cycle"],
                                 max_relative_change_in_window=float(rel_change[-window_cycles:].max()) if n > window_cycles else None,
                                 per_cycle_metric=per_cycle, rel_tol=rel_tol, periodicity_tol=periodicity_tol)
    window = per_cycle[-window_cycles:]
    t0, t1 = window[0]["t_start"], window[-1]["t_end"]
    mask = (t >= t0 - 1e-15) & (t <= t1 + 1e-15)
    perr = periodicity_error(t[mask], x[mask], period)
    ok = perr <= periodicity_tol
    reason = "periodic steady state reached" if ok else f"periodicity error {perr:.3e} exceeds {periodicity_tol:g}"
    return SteadyStateResult(ok, reason, t0=t0, t1=t1, cycles_in_window=window_cycles, cycles_available=n,
                             converged_from_cycle=per_cycle[converged_from]["cycle"],
                             max_relative_change_in_window=float(rel_change[-window_cycles:].max()),
                             periodicity_error=perr, per_cycle_metric=per_cycle, rel_tol=rel_tol, periodicity_tol=periodicity_tol)
