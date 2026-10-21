"""Periodic steady-state detection on a synthetic sine with a decaying DC offset."""

from __future__ import annotations

import json

import numpy as np
import pytest

from aipe_simulation.waveforms.steady_state import SteadyStateResult, find_steady_state_window

F_SW = 100e3
T = 1.0 / F_SW
OMEGA = 2.0 * np.pi * F_SW
A = 10.0  # sine amplitude
B = 5.0  # initial DC offset


def make_signal(n_cycles: int, tau: float, points_per_cycle: int = 1000) -> tuple[np.ndarray, np.ndarray]:
    """i(t) = A sin(wt) + B exp(-t/tau) on a mildly non-uniform grid covering exactly n_cycles periods.

    Cycle boundaries k*T deliberately fall between samples, as in solver output: the
    per-cycle metric then carries an O(dt/T) normalisation bias (the cycle average is
    taken over the span of the samples inside the window), here below 1.5e-3.
    """
    n = n_cycles * points_per_cycle + 1
    u = np.linspace(0.0, 1.0, n)
    t = n_cycles * T * (u + 0.3 * np.sin(2 * np.pi * 5 * u) / (2 * np.pi * 5))
    t[0], t[-1] = 0.0, n_cycles * T
    return t, A * np.sin(OMEGA * t) + B * np.exp(-t / tau)


def test_long_time_constant_is_reported_as_not_steady():
    t, x = make_signal(12, tau=50 * T)
    res = find_steady_state_window(t, x, T, 0.0, rel_tol=1e-3, window_cycles=4)
    assert isinstance(res, SteadyStateResult)
    assert res.ok is False
    assert res.t0 is None and res.t1 is None
    assert res.reason.startswith("cycle metric still changing")
    assert res.cycles_available == 12
    assert res.cycles_in_window == 0
    assert len(res.per_cycle_metric) == 12
    assert res.max_relative_change_in_window is not None and res.max_relative_change_in_window > 1e-3
    # Fewer than window_cycles converged cycles -> convergence can only start in the last three.
    assert res.converged_from_cycle is not None and res.converged_from_cycle >= 9
    values = np.array([c["value"] for c in res.per_cycle_metric])
    assert np.all(np.diff(values) < 0)  # the offset decays monotonically


def test_decayed_offset_is_steady_with_four_cycle_window():
    t, x = make_signal(12, tau=T / 3)
    res = find_steady_state_window(t, x, T, 0.0, rel_tol=1e-3, window_cycles=4, periodicity_tol=1e-2)
    assert res.ok is True
    assert res.reason == "periodic steady state reached"
    assert res.cycles_in_window == 4
    assert res.cycles_available == 12
    # Window is the last four complete cycles, aligned to whole periods from t_origin.
    assert res.t0 == pytest.approx(8 * T, abs=1e-15)
    assert res.t1 == pytest.approx(12 * T, abs=1e-15)
    assert (res.t1 - res.t0) / T == pytest.approx(4.0, abs=1e-9)
    assert res.t0 / T == pytest.approx(round(res.t0 / T), abs=1e-9)
    assert res.converged_from_cycle is not None and res.converged_from_cycle <= 8
    assert res.max_relative_change_in_window is not None and res.max_relative_change_in_window <= 1e-3
    assert res.periodicity_error is not None and res.periodicity_error < 1e-4
    assert res.rel_tol == 1e-3 and res.periodicity_tol == 1e-2
    # per-cycle metric populated for every complete cycle
    per_cycle = res.per_cycle_metric
    assert [c["cycle"] for c in per_cycle] == list(range(12))
    for c in per_cycle:
        assert set(c) == {"cycle", "t_start", "t_end", "value"}
        assert c["t_start"] == pytest.approx(c["cycle"] * T, abs=1e-15)
        assert c["t_end"] == pytest.approx((c["cycle"] + 1) * T, abs=1e-15)
    values = [c["value"] for c in per_cycle]
    assert values[0] > values[-1] * 1.02  # the start-up offset is visible in the first cycle
    # Tolerance covers the O(dt/T) bias of a cycle whose boundaries fall between samples.
    assert values[-4:] == pytest.approx([A / np.sqrt(2.0)] * 4, rel=2e-3)
    json.dumps(res.to_dict())  # the result must be JSON serialisable for summary.json


def test_window_cycles_sets_the_window_length():
    t, x = make_signal(12, tau=T / 3)
    res = find_steady_state_window(t, x, T, 0.0, window_cycles=6)
    assert res.ok is True
    assert res.cycles_in_window == 6
    assert res.t0 == pytest.approx(6 * T, abs=1e-15)
    assert res.t1 == pytest.approx(12 * T, abs=1e-15)


def test_window_is_aligned_to_the_requested_origin():
    t, x = make_signal(12, tau=T / 3)
    origin = 0.25 * T
    res = find_steady_state_window(t, x, T, origin, window_cycles=4)
    assert res.ok is True
    assert res.cycles_available == 11  # [0.25T, 11.25T] holds eleven complete cycles
    assert (res.t0 - origin) / T == pytest.approx(round((res.t0 - origin) / T), abs=1e-9)
    assert res.t1 == pytest.approx(11.25 * T, abs=1e-15)
    assert res.t0 == pytest.approx(7.25 * T, abs=1e-15)


def test_fewer_cycles_than_needed():
    t, x = make_signal(3, tau=T / 3)
    res = find_steady_state_window(t, x, T, 0.0, window_cycles=4)
    assert res.ok is False
    assert res.reason == "only 3 complete cycles available; need at least 5"
    assert res.cycles_available == 3
    assert res.t0 is None and res.t1 is None
    assert res.converged_from_cycle is None
    assert len(res.per_cycle_metric) == 3
    json.dumps(res.to_dict())


def test_subharmonic_fails_the_periodicity_check():
    """A period-2T component leaves the per-cycle RMS constant but breaks periodicity in T."""
    t, _ = make_signal(12, tau=T / 3)
    x = A * np.sin(OMEGA * t) + 0.3 * A * np.sin(OMEGA * t / 2)
    res = find_steady_state_window(t, x, T, 0.0, rel_tol=1e-3, window_cycles=4, periodicity_tol=1e-2)
    assert res.ok is False
    assert res.reason.startswith("periodicity error")
    assert res.t0 is not None and res.t1 is not None  # a window was formed, then rejected
    assert res.periodicity_error is not None and res.periodicity_error > 0.3
    assert res.max_relative_change_in_window is not None and res.max_relative_change_in_window <= 1e-3


def test_custom_metric_is_used():
    t, x = make_signal(12, tau=T / 3)
    res = find_steady_state_window(t, x + 2.0, T, 0.0, window_cycles=4, metric=lambda tt, xx: float(np.max(xx)))
    assert res.ok is True
    assert res.per_cycle_metric[-1]["value"] == pytest.approx(A + 2.0, rel=1e-4)
