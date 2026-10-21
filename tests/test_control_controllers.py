"""Discrete PI / DF22 compensators, Tustin discretisation and z-plane loop analysis."""

from __future__ import annotations

import math

import numpy as np
import pytest

from aipe_simulation.control.controllers import (Df22Compensator, DiscretePI, design_2p2z, design_pi_for_static_plant,
                                                 stability_margins, tustin_2p2z)
from aipe_simulation.control.ztf import ZTransfer

TS = 10e-6


def test_ztransfer_algebra_evaluation_and_simulation():
    h1 = ZTransfer([1.0, 0.5], [1.0, -0.3])
    h2 = ZTransfer([2.0], [1.0, 0.1])
    z = np.exp(1j * np.linspace(0.1, 3.0, 7))
    np.testing.assert_allclose((h1 * h2)(z), h1(z) * h2(z))
    np.testing.assert_allclose((h1 + h2)(z), h1(z) + h2(z))
    np.testing.assert_allclose((h1 - h2)(z), h1(z) - h2(z))
    np.testing.assert_allclose((2.0 * h1)(z), 2.0 * h1(z))
    np.testing.assert_allclose((h1 / h2)(z), h1(z) / h2(z))
    np.testing.assert_allclose(h1.feedback()(z), h1(z) / (1 + h1(z)))
    np.testing.assert_allclose(h1.feedback(h2)(z), h1(z) / (1 + h1(z) * h2(z)))
    np.testing.assert_allclose(ZTransfer.delay(2)(z), z ** -2.0)
    np.testing.assert_allclose(h1.delayed(1)(z), h1(z) / z)
    np.testing.assert_allclose(h1.poles(), [0.3])
    np.testing.assert_allclose(h1.zeros(), [-0.5])
    assert h1.dc_gain() == pytest.approx(1.5 / 0.7)
    u = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
    y = h1.simulate(u)
    expected = [1.0, 0.5 + 0.3 * 1.0, 0.3 * (0.5 + 0.3), 0.3 ** 2 * 0.8, 0.3 ** 3 * 0.8]
    np.testing.assert_allclose(y, expected)
    np.testing.assert_allclose(h1.freqresp(0.0, TS), h1(1.0 + 0j))
    assert ZTransfer([1.0], [1.0, -1.0]).is_stable() is False  # integrator
    assert ZTransfer([1.0], [1.0, -0.99]).is_stable() is True
    with pytest.raises(ValueError):
        ZTransfer([1.0], [0.0, 1.0])
    with pytest.raises(ZeroDivisionError):
        h1 / ZTransfer.delay(1)
    d = h1.to_dict()
    assert d["num_z_inverse"] == [1.0, 0.5] and d["den_z_inverse"] == [1.0, -0.3]


def test_discrete_pi_behaviour_and_transfer_function():
    pi = DiscretePI(kp=2.0, ki=100.0, ts=1e-3)
    outputs = [pi.step(1.0) for _ in range(5)]
    np.testing.assert_allclose(outputs, [2.0 + 0.1 * (k + 1) for k in range(5)])
    assert pi.ki_per_sample == pytest.approx(0.1)
    np.testing.assert_allclose(pi.transfer_function().simulate(np.ones(5)), outputs)
    # saturation with clamping anti-windup
    sat = DiscretePI(kp=2.0, ki=100.0, ts=1e-3, u_max=3.0, u_min=-3.0)
    for _ in range(50):
        u = sat.step(1.0)
    assert u == 3.0 and sat.saturated is True
    assert sat.integrator <= 3.0 - 2.0 + 0.1 + 1e-12  # integrator frozen near the saturation boundary
    assert sat.step(-1.0) < 3.0  # leaves saturation immediately: no wind-up
    # tracking anti-windup against a downstream limiter
    tracked = DiscretePI(kp=1.0, ki=0.0, ts=1e-3, k_tracking=1.0)
    tracked.reset(u0=5.0, error=0.0)
    assert tracked.step(0.0) == pytest.approx(5.0)
    assert tracked.step(0.0, u_applied=4.0) == pytest.approx(4.0)  # integrator pulled to the applied value
    untracked = DiscretePI(kp=1.0, ki=0.0, ts=1e-3, k_tracking=0.0)
    untracked.reset(u0=5.0)
    assert untracked.step(0.0, u_applied=4.0) == pytest.approx(5.0)
    # bumpless reset
    pi.reset(u0=0.7, error=0.2)
    assert pi.step(0.2) == pytest.approx(0.7 + pi.ki_per_sample * 0.2)
    d = pi.to_dict()
    assert d["kp"] == 2.0 and "u[k] = Kp e[k] + x[k]" in d["structure"]
    for bad in (dict(kp=1.0, ki=1.0, ts=0.0), dict(kp=1.0, ki=1.0, ts=1e-3, u_min=1.0, u_max=0.0),
                dict(kp=-1.0, ki=1.0, ts=1e-3), dict(kp=1.0, ki=1.0, ts=1e-3, k_tracking=2.0)):
        with pytest.raises(ValueError):
            DiscretePI(**bad)


def test_df22_matches_transfer_function_and_clamps_without_windup():
    b, a = tustin_2p2z(1000.0, 300.0, 300.0, 5000.0, TS, prewarp_hz=300.0)
    comp = Df22Compensator(*b, a[1], a[2])
    rng = np.random.default_rng(0)
    e = rng.normal(size=200)
    y = np.array([comp.step(v) for v in e])
    np.testing.assert_allclose(y, comp.transfer_function().simulate(e), rtol=1e-9, atol=1e-9)
    clamped = Df22Compensator(*b, a[1], a[2], y_min=-1.0, y_max=1.0)
    for _ in range(500):
        out = clamped.step(1.0)
    assert out == 1.0 and clamped.saturated is True and clamped.y1 == 1.0
    assert clamped.step(-1.0) < 1.0 - 1e-6  # stored clamped history: no wind-up
    comp.reset(y0=5.0, error=0.0)
    assert comp.step(0.0) == pytest.approx(5.0)  # integrating compensator (a1 + a2 = -1) holds its output
    d = comp.to_dict()
    assert d["difference_equation"].startswith("y[n] = b0 e[n]")
    assert len(d["poles_z"]) == 2 and len(d["zeros_z"]) == 2


def test_tustin_2p2z_prewarp_and_integrator_pole():
    k, fz1, fz2, fp, fc = 1000.0, 300.0, 600.0, 5000.0, 300.0
    b, a = tustin_2p2z(k, fz1, fz2, fp, TS, prewarp_hz=fc)
    assert a[0] == 1.0 and len(b) == 3 and len(a) == 3
    assert 1 + a[1] + a[2] == pytest.approx(0.0, abs=1e-12)  # pole at z = 1
    tf = ZTransfer(b, a)

    def prototype(f: float) -> complex:
        s = 1j * 2 * math.pi * f
        return k * (1 + s / (2 * math.pi * fz1)) * (1 + s / (2 * math.pi * fz2)) / (s * (1 + s / (2 * math.pi * fp)))

    hz = complex(tf.freqresp(fc, TS))
    assert abs(hz) == pytest.approx(abs(prototype(fc)), rel=1e-9)
    assert math.degrees(np.angle(hz)) == pytest.approx(math.degrees(np.angle(prototype(fc))), abs=1e-6)
    for f in (30.0, 100.0, 1000.0):
        assert abs(complex(tf.freqresp(f, TS))) == pytest.approx(abs(prototype(f)), rel=2e-2)
    with pytest.raises(ValueError):
        tustin_2p2z(k, fz1, fz2, fp, TS, prewarp_hz=60e3)
    with pytest.raises(ValueError):
        tustin_2p2z(-1.0, fz1, fz2, fp, TS)


def test_stability_margins_of_delayed_integrator_match_closed_form():
    # L(z) = K z^-1 / (1 - z^-1) = K / (e^{j theta} - 1): |L| = K / (2 sin(theta/2)), phase = -90 deg - theta/2
    k = 0.1
    loop = ZTransfer([0.0, k], [1.0, -1.0])
    m = stability_margins(loop, TS)
    theta_c = 2 * math.asin(k / 2)
    assert m["gain_crossover_hz"] == pytest.approx(theta_c / (2 * math.pi * TS), rel=1e-3)
    assert m["phase_margin_deg"] == pytest.approx(90.0 - math.degrees(theta_c) / 2, abs=0.05)
    assert m["gain_margin_db"] == pytest.approx(20 * math.log10(2 / k), abs=0.05)
    assert m["phase_crossover_hz"] == pytest.approx(0.5 / TS, rel=2e-3)
    assert m["closed_loop_stable"] is True and len(m["all_gain_crossovers"]) == 1
    unstable = stability_margins(ZTransfer([0.0, 2.5], [1.0, -1.0]), TS)
    assert unstable["closed_loop_stable"] is False
    assert unstable["gain_margin_db"] < 0
    with pytest.raises(ValueError):
        stability_margins(loop, TS, f_min=1e5)


def test_design_pi_for_static_plant_hits_targets():
    k_plant = 54.5674  # A/rad at the nominal 10 kW operating point
    d = design_pi_for_static_plant(k_plant, 2000.0, TS, delay_samples=2, high_frequency_gain=0.25)
    m = d["margins"]
    assert m["gain_crossover_hz"] == pytest.approx(2000.0, rel=1e-3)
    assert 80.0 < m["phase_margin_deg"] < 100.0
    assert m["gain_margin_db"] == pytest.approx(10.0, abs=1.0)
    assert m["closed_loop_stable"] is True
    assert d["kp"] == pytest.approx(0.25 / k_plant)
    assert d["ki_per_sample"] * k_plant == pytest.approx(2 * math.pi * 2000.0 * TS, rel=0.08)
    assert isinstance(d["pi"], DiscretePI) and d["pi"].u_max == math.inf
    # the delay only costs phase, not crossover
    d0 = design_pi_for_static_plant(k_plant, 2000.0, TS, delay_samples=0, high_frequency_gain=0.25)
    assert d0["margins"]["phase_margin_deg"] > m["phase_margin_deg"] + 10.0
    assert d0["margins"]["gain_crossover_hz"] == pytest.approx(2000.0, rel=1e-3)
    with pytest.raises(ValueError):
        design_pi_for_static_plant(k_plant, 60e3, TS)
    with pytest.raises(ValueError):
        design_pi_for_static_plant(k_plant, 2000.0, TS, high_frequency_gain=1.0)


def test_design_2p2z_meets_crossover_and_phase_margin():
    c2 = 400e-6
    rest = ZTransfer([0.0, TS / c2], [1.0, -1.0]).delayed(1)  # capacitor plant with one delay, unity inner loop
    d = design_2p2z(rest, TS, 300.0, pm_target_deg=60.0, f_pole=5000.0, y_min=-30.0, y_max=30.0)
    m = d["margins"]
    assert m["gain_crossover_hz"] == pytest.approx(300.0, rel=1e-3)
    assert m["phase_margin_deg"] == pytest.approx(60.0, abs=0.5)
    assert m["closed_loop_stable"] is True and m["gain_margin_db"] > 10.0
    c = d["coefficients"]
    assert 1 + c["a1"] + c["a2"] == pytest.approx(0.0, abs=1e-12)
    assert d["prototype"]["f_zero_hz"] > 0 and d["prototype"]["f_pole_hz"] == 5000.0
    comp = d["compensator"]
    assert isinstance(comp, Df22Compensator) and comp.y_max == 30.0
    # explicit zero placement is honoured; infeasible phase-margin targets are rejected
    fixed = design_2p2z(rest, TS, 300.0, f_zero=250.0)
    assert fixed["prototype"]["f_zero_hz"] == 250.0
    assert fixed["margins"]["gain_crossover_hz"] == pytest.approx(300.0, rel=1e-3)
    with pytest.raises(ValueError, match="infeasible"):
        design_2p2z(rest, TS, 300.0, pm_target_deg=179.0)
    with pytest.raises(ValueError):
        design_2p2z(rest, TS, 60e3)
