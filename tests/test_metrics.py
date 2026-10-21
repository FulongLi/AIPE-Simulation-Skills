"""Engineering metrics checked against analytic signals on a deliberately non-uniform grid.

The grid is a smooth warp of a uniform grid whose local step varies by a factor
of about 2.6 (dt/du = 1 + 0.45 cos), as a variable-step solver would produce.
"""

from __future__ import annotations

import numpy as np
import pytest

from aipe_simulation.waveforms import metrics as m

F_SW = 100e3
T = 1.0 / F_SW
OMEGA = 2.0 * np.pi * F_SW


def warped_grid(t_end: float, n: int = 6001, strength: float = 0.45, lobes: int = 7) -> np.ndarray:
    """Strictly increasing grid from 0 to t_end (both exact) with a strongly varying step."""
    u = np.linspace(0.0, 1.0, n)
    t = t_end * (u + strength * np.sin(2 * np.pi * lobes * u) / (2 * np.pi * lobes))
    t[0], t[-1] = 0.0, t_end
    return t


@pytest.fixture(scope="module")
def grid() -> np.ndarray:
    return warped_grid(3 * T)


@pytest.fixture(scope="module")
def dt_max(grid) -> float:
    return float(np.diff(grid).max())


def test_grid_is_strictly_increasing_and_non_uniform(grid):
    dt = np.diff(grid)
    assert np.all(dt > 0)
    assert dt.max() / dt.min() > 2.0
    assert grid[0] == 0.0 and grid[-1] == 3 * T


# ---------------------------------------------------------------------------
# averages, rms, power
# ---------------------------------------------------------------------------
def test_rms_and_average_of_sine_over_whole_periods(grid):
    x = 3.0 * np.sin(OMEGA * grid)
    assert m.rms(grid, x) == pytest.approx(3.0 / np.sqrt(2.0), rel=1e-3)
    assert abs(m.average(grid, x)) < 1e-3 * 3.0
    y = x + 1.25
    assert m.average(grid, y) == pytest.approx(1.25, rel=1e-3)
    assert m.rms(grid, y) == pytest.approx(np.sqrt(4.5 + 1.25 ** 2), rel=1e-3)


def test_integrate_half_rectified_sine(grid):
    x = np.clip(np.sin(OMEGA * grid), 0.0, None)
    assert m.integrate(grid, x) == pytest.approx(3 * 2.0 / OMEGA, rel=1e-3)
    assert m.integrate(grid, np.ones_like(grid)) == pytest.approx(3 * T, rel=1e-12)


def test_average_power(grid):
    v = 10.0 * np.sin(OMEGA * grid)
    i_lag = 2.0 * np.sin(OMEGA * grid - np.pi / 3)
    assert m.average_power(grid, v, i_lag) == pytest.approx(10.0 * 2.0 / 2 * np.cos(np.pi / 3), rel=1e-3)
    assert m.average_power(grid, v, 2.0 * np.sin(OMEGA * grid)) == pytest.approx(10.0, rel=1e-3)
    assert abs(m.average_power(grid, v, 2.0 * np.cos(OMEGA * grid))) < 1e-3 * 10.0


def test_peak_and_ripple(grid):
    x = 1.0 + 0.5 * np.sin(OMEGA * grid)
    pk = m.peak(grid, x)
    assert pk["max"] == pytest.approx(1.5, rel=1e-5)
    assert pk["min"] == pytest.approx(0.5, rel=1e-4)
    assert pk["abs_max"] == pytest.approx(1.5, rel=1e-5)
    assert (pk["t_max"] % T) / T == pytest.approx(0.25, abs=1e-3)
    assert (pk["t_min"] % T) / T == pytest.approx(0.75, abs=1e-3)
    rp = m.ripple(grid, x)
    assert rp["peak_to_peak"] == pytest.approx(1.0, rel=1e-4)
    assert rp["mean"] == pytest.approx(1.0, rel=1e-3)
    assert rp["relative_peak_to_peak"] == pytest.approx(1.0, rel=2e-3)


# ---------------------------------------------------------------------------
# crossings and conduction intervals
# ---------------------------------------------------------------------------
def test_threshold_crossings_of_sine_at_zero(grid, dt_max):
    phase = 0.3
    x = np.sin(OMEGA * grid + phase)
    expected_rising = np.array([(2 * np.pi * k - phase) / OMEGA for k in (1, 2, 3)])
    expected_falling = np.array([(np.pi + 2 * np.pi * k - phase) / OMEGA for k in (0, 1, 2)])
    rising = m.threshold_crossings(grid, x, 0.0, "rising")
    falling = m.threshold_crossings(grid, x, 0.0, "falling")
    both = m.threshold_crossings(grid, x, 0.0, "both")
    assert rising.shape == (3,) and falling.shape == (3,) and both.shape == (6,)
    np.testing.assert_allclose(rising, expected_rising, atol=dt_max)
    np.testing.assert_allclose(falling, expected_falling, atol=dt_max)
    np.testing.assert_allclose(both, np.sort(np.concatenate([expected_rising, expected_falling])), atol=dt_max)
    assert np.all(np.diff(both) > 0)
    # Linear interpolation is far better than one sample on a smooth signal.
    np.testing.assert_allclose(rising, expected_rising, atol=0.02 * dt_max)


def test_threshold_crossings_at_nonzero_level(grid, dt_max):
    x = 2.0 * np.sin(OMEGA * grid)
    level = 1.0  # sin = 0.5 at pi/6 (rising) and 5 pi/6 (falling)
    rising = m.threshold_crossings(grid, x, level, "rising")
    falling = m.threshold_crossings(grid, x, level, "falling")
    np.testing.assert_allclose(rising, np.array([k * T + T / 12 for k in range(3)]), atol=dt_max)
    np.testing.assert_allclose(falling, np.array([k * T + 5 * T / 12 for k in range(3)]), atol=dt_max)
    assert m.threshold_crossings(grid, x, 5.0).size == 0


def test_conduction_intervals_of_half_rectified_sine(grid, dt_max):
    A = 4.0
    i = np.clip(A * np.sin(OMEGA * grid), 0.0, None)
    threshold = 1e-3 * A
    intervals = m.conduction_intervals(grid, i, threshold)
    assert len(intervals) == 3
    for k, iv in enumerate(intervals):
        assert iv["t_start"] == pytest.approx(k * T, abs=1.5 * dt_max)
        assert iv["t_end"] == pytest.approx(k * T + T / 2, abs=1.5 * dt_max)
        assert iv["duration"] == pytest.approx(T / 2, abs=2 * dt_max)
        assert iv["charge"] == pytest.approx(2 * A / OMEGA, rel=1e-3)
        assert iv["mean_current"] == pytest.approx(2 * A / np.pi, rel=5e-3)
        assert iv["rms_current"] == pytest.approx(A / np.sqrt(2.0), rel=5e-3)
        assert iv["peak_abs"] == pytest.approx(A, rel=1e-4)
    # |i| is used: negative humps are intervals too, with negative charge.
    negative = m.conduction_intervals(grid, -i, threshold)
    assert len(negative) == 3
    for iv in negative:
        assert iv["charge"] == pytest.approx(-2 * A / OMEGA, rel=1e-3)
        assert iv["peak_abs"] == pytest.approx(A, rel=1e-4)
    assert m.conduction_intervals(grid, i, 2 * A) == []


# ---------------------------------------------------------------------------
# volt-seconds, periodicity and symmetry
# ---------------------------------------------------------------------------
def test_volt_seconds_of_square_wave(grid, dt_max):
    V = 100.0
    v = np.where(np.sin(OMEGA * grid) >= 0.0, V, -V)
    vs = m.volt_seconds(grid, v, T, T)  # second cycle [T, 2T]
    assert abs(vs["net_volt_seconds"]) <= 3 * V * dt_max
    assert vs["flux_linkage_peak_to_peak"] == pytest.approx(V * T / 2, abs=3 * V * dt_max)
    assert vs["positive_volt_seconds"] == pytest.approx(V * T / 2, abs=3 * V * dt_max)
    assert vs["relative_imbalance"] < 1e-2
    # Flux linkage of the sine: lambda(t) = (V/omega)(1 - cos), pp = 2V/omega, exactly balanced.
    vs_sine = m.volt_seconds(grid, V * np.sin(OMEGA * grid), 0.0, T)
    assert vs_sine["flux_linkage_peak_to_peak"] == pytest.approx(2 * V / OMEGA, rel=1e-3)
    assert abs(vs_sine["net_volt_seconds"]) < 1e-3 * 2 * V / OMEGA
    with pytest.raises(ValueError, match="fewer than two samples"):
        m.volt_seconds(grid, v, 10 * T, T)


def test_periodicity_error(grid):
    x = np.sin(OMEGA * grid)
    assert m.periodicity_error(grid, x, T) < 1e-4
    assert m.periodicity_error(grid, x, T, t0=T) < 1e-4
    ramp = grid / (3 * T)
    assert m.periodicity_error(grid, ramp, T) > 0.3  # exact value 1/3
    assert m.periodicity_error(grid, ramp, T) == pytest.approx(1.0 / 3.0, rel=1e-2)
    with pytest.raises(ValueError, match="shorter than one period"):
        m.periodicity_error(grid[:50], x[:50], T)


def test_half_wave_symmetry_error(grid):
    x = np.sin(OMEGA * grid)
    assert m.half_wave_symmetry_error(grid, x, T) < 1e-4
    offset = x + 0.5
    assert m.half_wave_symmetry_error(grid, offset, T) > 0.5  # exact value 1.0 / 1.5
    assert m.half_wave_symmetry_error(grid, offset, T) == pytest.approx(1.0 / 1.5, rel=1e-2)
    assert m.half_wave_symmetry_error(grid, np.abs(x), T) == pytest.approx(2.0, rel=1e-2)
    with pytest.raises(ValueError, match="shorter than half a period"):
        m.half_wave_symmetry_error(grid[:20], x[:20], T)


# ---------------------------------------------------------------------------
# cycle values and interpolation
# ---------------------------------------------------------------------------
def test_cycle_values_count_and_alignment(grid):
    x = 2.0 * np.sin(OMEGA * grid)
    cycles = m.cycle_values(grid, x, 0.0, T)
    assert [c["cycle"] for c in cycles] == [0, 1, 2]
    for c in cycles:
        assert c["t_start"] == pytest.approx(c["cycle"] * T, abs=1e-15)
        assert c["t_end"] == pytest.approx((c["cycle"] + 1) * T, abs=1e-15)
        assert c["value"] == pytest.approx(2.0 / np.sqrt(2.0), rel=1e-3)
    shifted = m.cycle_values(grid, x, 0.25 * T, T)
    assert [c["cycle"] for c in shifted] == [0, 1]
    assert shifted[0]["t_start"] == pytest.approx(0.25 * T, abs=1e-15)
    assert shifted[1]["t_end"] == pytest.approx(2.25 * T, abs=1e-15)
    keep = grid >= 0.3 * T
    partial = m.cycle_values(grid[keep], x[keep], 0.0, T)
    assert [c["cycle"] for c in partial] == [1, 2]
    averages = m.cycle_values(grid, x + 1.0, 0.0, T, fn=m.average)
    assert [c["value"] for c in averages] == pytest.approx([1.0, 1.0, 1.0], rel=1e-3)


def test_interp_at_sides_on_a_step():
    base = np.linspace(0.0, 1.0, 11)
    t_step, eps = 0.505, 1e-6
    t = np.sort(np.concatenate([base, [t_step - eps, t_step + eps]]))
    x = (t >= t_step).astype(float)
    before = m.interp_at(t, x, t_step, side="before")
    after = m.interp_at(t, x, t_step, side="after")
    exact = m.interp_at(t, x, t_step)
    assert before.shape == after.shape == exact.shape == (1,)
    assert float(before[0]) == pytest.approx(0.0, abs=1e-12)
    assert float(after[0]) == pytest.approx(1.0, abs=1e-12)
    assert float(exact[0]) == pytest.approx(0.5, abs=1e-9)
    assert before[0] <= exact[0] <= after[0]
    far = np.array([0.2, 0.8])
    np.testing.assert_allclose(m.interp_at(t, x, far, side="before"), [0.0, 1.0])
    np.testing.assert_allclose(m.interp_at(t, x, far, side="after"), [0.0, 1.0])
    np.testing.assert_allclose(m.interp_at(t, x, far), [0.0, 1.0])
    # Exact interpolation on a smooth signal returns the sampled values at the samples.
    y = np.sin(2 * np.pi * t)
    np.testing.assert_allclose(m.interp_at(t, y, t[3:6]), y[3:6])


def test_input_validation():
    t = np.array([0.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        m.rms(t, np.array([1.0, 2.0]))
    with pytest.raises(ValueError):
        m.average(np.array([0.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        m.integrate(np.zeros((2, 2)), np.zeros((2, 2)))
    with pytest.raises(ValueError, match="span"):
        m.average(np.array([1.0, 1.0]), np.array([1.0, 2.0]))
