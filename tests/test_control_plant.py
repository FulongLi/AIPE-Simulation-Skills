"""Cycle-averaged DAB plant: closed forms, lossless series current, exact discretisation, small signal."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from aipe_simulation.control import plant as P
from aipe_simulation.control.ztf import ZTransfer

_trapezoid = getattr(np, "trapezoid", None) or np.trapz  # numpy < 2.0 compatibility

V1, V2, N, F, L = 800.0, 400.0, 2.0, 100e3, 35e-6
T = 1.0 / F
PHI_NOM = math.radians(22.5)
I_L0 = 14.285714285714288  # analytic i_L at the centre of the primary positive half-cycle, 10 kW point (see tests/test_dab_ngspice.py)


def test_nominal_operating_point_closed_forms():
    assert P.sps_power(V1, V2, N, F, L, PHI_NOM) == pytest.approx(10000.0)
    assert P.sps_output_current(V1, N, F, L, PHI_NOM) == pytest.approx(25.0)
    assert P.sps_max_power(V1, V2, N, F, L) == pytest.approx(640000.0 / 28.0)
    assert P.phase_shift_for_power(V1, V2, N, F, L, 10000.0) == pytest.approx(PHI_NOM)
    assert P.phase_shift_for_output_current(V1, N, F, L, -25.0) == pytest.approx(-PHI_NOM)
    assert P.phase_shift_for_output_current(V1, N, F, L, 0.0) == 0.0
    assert P.series_current_at(V1, V2, N, F, L, PHI_NOM, 0.0, "centre") == pytest.approx(I_L0)
    assert P.series_current_peak(V1, V2, N, F, L, PHI_NOM) == pytest.approx(I_L0)
    assert P.series_current_rms(V1, V2, N, F, L, PHI_NOM) == pytest.approx(13.6775, rel=1e-4)
    # reversal: odd symmetry in phi
    assert P.sps_power(V1, V2, N, F, L, -PHI_NOM) == pytest.approx(-10000.0)
    assert P.sps_output_current(V1, N, F, L, -PHI_NOM) == pytest.approx(-25.0)
    assert P.series_current_at(V1, V2, N, F, L, -PHI_NOM, 0.0, "centre") == pytest.approx(-I_L0)
    # small-signal gains
    k_i = P.output_current_gain(V1, N, F, L, PHI_NOM)
    assert k_i == pytest.approx(N * V1 * (math.pi - 2 * PHI_NOM) / (2 * math.pi ** 2 * F * L))
    assert k_i == pytest.approx(54.5674, rel=1e-4)
    assert P.output_current_gain(V1, N, F, L, 0.0) == pytest.approx(72.7565, rel=1e-4)
    assert P.power_gain(V1, V2, N, F, L, PHI_NOM) == pytest.approx(V2 * k_i)
    h = 1e-6
    numeric = (P.sps_power(V1, V2, N, F, L, PHI_NOM + h) - P.sps_power(V1, V2, N, F, L, PHI_NOM - h)) / (2 * h)
    assert numeric == pytest.approx(P.power_gain(V1, V2, N, F, L, PHI_NOM), rel=1e-6)
    # the output current does not depend on V2 (phase-shift-controlled current source)
    assert P.sps_power(V1, 350.0, N, F, L, PHI_NOM) / 350.0 == pytest.approx(P.sps_output_current(V1, N, F, L, PHI_NOM))


@pytest.mark.parametrize("call", [
    lambda: P.sps_power(V1, V2, N, F, L, 2.0),
    lambda: P.sps_power(V1, V2, N, F, -L, PHI_NOM),
    lambda: P.sps_power(V1, -1.0, N, F, L, PHI_NOM),
    lambda: P.phase_shift_for_output_current(V1, N, F, L, 1e4),
    lambda: P.series_current_breakpoints(V1, V2, N, F, L, PHI_NOM, origin="middle"),
    lambda: P.output_current_gain(V1, N, F, L, float("nan")),
])
def test_invalid_inputs_raise(call):
    with pytest.raises(ValueError):
        call()


@pytest.mark.parametrize("phi_deg, v2", [(22.5, 400.0), (-22.5, 400.0), (10.0, 350.0), (35.0, 450.0), (-60.0, 300.0), (90.0, 400.0), (0.0, 400.0)])
def test_series_current_waveform_properties(phi_deg, v2):
    phi = math.radians(phi_deg)
    t = np.linspace(0.0, T, 4001)
    i_c = np.array([P.series_current_at(V1, v2, N, F, L, phi, tk, "centre") for tk in t])
    i_r = np.array([P.series_current_at(V1, v2, N, F, L, phi, tk + T / 4, "rising_edge") for tk in t])
    np.testing.assert_allclose(i_c, i_r, atol=1e-9)
    # half-wave antisymmetry and periodicity
    i_half = np.array([P.series_current_at(V1, v2, N, F, L, phi, tk + T / 2, "centre") for tk in t])
    np.testing.assert_allclose(i_half, -i_c, atol=1e-9)
    assert P.series_current_at(V1, v2, N, F, L, phi, T, "centre") == pytest.approx(i_c[0], abs=1e-9)
    # power from the waveform integral equals the closed form: v_ab = +V1 on the centred positive half-cycle
    v_ab = np.where((t < T / 4) | (t > 3 * T / 4), V1, -V1)
    p_wave = _trapezoid(v_ab * i_c, t) / T
    assert p_wave == pytest.approx(P.sps_power(V1, v2, N, F, L, phi), rel=2e-3, abs=1.0)
    # the exact peak sits on a breakpoint that the sample grid may miss by up to half a grid step
    peak = P.series_current_peak(V1, v2, N, F, L, phi)
    assert peak >= np.max(np.abs(i_c)) - 1e-9 and peak == pytest.approx(np.max(np.abs(i_c)), rel=5e-3)
    assert P.series_current_rms(V1, v2, N, F, L, phi) == pytest.approx(math.sqrt(_trapezoid(i_c ** 2, t) / T), rel=2e-3)
    pts = P.series_current_breakpoints(V1, v2, N, F, L, phi, "centre")
    assert pts[0][0] == 0.0 and pts[-1][0] == pytest.approx(T)
    assert pts[0][1] == pytest.approx(pts[-1][1])
    assert peak == max(abs(i) for _, i in pts)


def test_short_circuit_circulating_current():
    # with the output shorted (V2' = 0) the lossless inductor sees +-V1 and the peak is V1 T / (4 L) regardless of phi
    for phi_deg in (0.0, 15.0, 45.0):
        assert P.series_current_peak(V1, 0.0, N, F, L, math.radians(phi_deg)) == pytest.approx(V1 * T / (4 * L))
    assert P.sps_power(V1, 0.0, N, F, L, PHI_NOM) == 0.0
    assert P.sps_output_current(V1, N, F, L, PHI_NOM) == pytest.approx(25.0)  # the current source persists into a short


def test_plant_step_is_exact_zoh_discretisation():
    params = P.DabSpsPlantParameters(c2=400e-6, r_load=16.0, ts=10e-6)
    plant = P.DabSpsPlant(params, v2_initial=380.0)
    i2 = P.sps_output_current(V1, N, F, L, PHI_NOM)
    v_inf = params.r_load * i2
    for k in range(1, 201):
        out = plant.step(PHI_NOM)
        expected = v_inf + (380.0 - v_inf) * math.exp(-k * params.ts / (params.r_load * params.c2))
        assert out["v2"] == pytest.approx(expected, rel=1e-12)
        assert out["i2"] == pytest.approx(i2)
        assert out["i1"] == pytest.approx(P.sps_power(V1, out["v2"], N, F, L, PHI_NOM) / V1, rel=5e-3)  # v2 at interval start
    assert plant.t == pytest.approx(200 * params.ts)
    # current-source load: linear ramp
    cs = P.DabSpsPlant(P.DabSpsPlantParameters(c2=400e-6, r_load=None, i_load=10.0, ts=10e-6), v2_initial=400.0)
    for k in range(1, 51):
        out = cs.step(PHI_NOM)
        assert out["v2"] == pytest.approx(400.0 + (25.0 - 10.0) * k * 10e-6 / 400e-6, rel=1e-12)
    # reverse power with a negative phase shift discharges the capacitor
    rev = P.DabSpsPlant(P.DabSpsPlantParameters(c2=400e-6, r_load=None, ts=10e-6), 400.0)
    assert rev.step(-PHI_NOM)["v2"] < 400.0 and rev.i2 == pytest.approx(-25.0)
    # disabled gates: no power transfer, no series current, RC decay only
    off = P.DabSpsPlant(P.DabSpsPlantParameters(c2=400e-6, r_load=16.0, ts=10e-6), 400.0)
    out = off.step(PHI_NOM, enabled=False)
    assert out["i2"] == 0.0 and out["i_l_peak"] == 0.0 and out["v2"] == pytest.approx(400.0 * math.exp(-10e-6 / (16.0 * 400e-6)))
    # the voltage never goes negative
    drained = P.DabSpsPlant(P.DabSpsPlantParameters(c2=1e-6, r_load=None, i_load=100.0, ts=10e-6), 0.5)
    assert drained.step(0.0)["v2"] == 0.0


def test_source_resistance_and_measurements():
    plant = P.DabSpsPlant(P.DabSpsPlantParameters(r_source=1.0, r_load=16.0), 400.0)
    out = plant.step(PHI_NOM)
    i1 = N * 400.0 * P.sps_g(PHI_NOM) / (2 * math.pi ** 2 * F * L)
    assert out["v1_bus"] == pytest.approx(V1 - 1.0 * i1)
    assert out["i2"] == pytest.approx(P.sps_output_current(out["v1_bus"], N, F, L, PHI_NOM))
    assert out["i2"] < 25.0
    m = plant.measurements()
    assert set(m) >= {"t", "v2", "i2", "i1", "p2", "v1_bus", "i_l_peak", "i_l_rms", "i_load", "phi", "enabled"}
    assert m["p2"] == pytest.approx(400.0 * out["i2"])
    plant.set_load(r_load=None, i_load=-5.0)
    assert plant.p.r_load is None and plant.p.i_load == -5.0
    with pytest.raises(ValueError):
        plant.set_load(r_load=-1.0)
    with pytest.raises(ValueError):
        P.DabSpsPlant(P.DabSpsPlantParameters(ts=1e-6))  # faster than one switching period
    with pytest.raises(ValueError):
        P.DabSpsPlant(P.DabSpsPlantParameters(), v2_initial=-1.0)


def test_small_signal_and_output_port_transfer_function():
    params = P.DabSpsPlantParameters(c2=400e-6, r_load=16.0, ts=10e-6)
    plant = P.DabSpsPlant(params, 400.0)
    ss = plant.small_signal(PHI_NOM)
    assert ss["dI2_dphi_A_per_rad"] == pytest.approx(54.5674, rel=1e-4)
    assert ss["dP_dphi_W_per_rad"] == pytest.approx(400.0 * 54.5674, rel=1e-4)
    assert ss["output_port_pole_Hz"] == pytest.approx(1.0 / (2 * math.pi * 16.0 * 400e-6))
    assert ss["phi_to_v2_dc_gain_V_per_rad"] == pytest.approx(16.0 * 54.5674, rel=1e-4)
    z = plant.output_port_tf()
    a = math.exp(-10e-6 / (16.0 * 400e-6))
    np.testing.assert_allclose(z.num, [0.0, 16.0 * (1 - a)])
    np.testing.assert_allclose(z.den, [1.0, -a])
    assert z.dc_gain() == pytest.approx(16.0)
    assert abs(complex(z.poles()[0])) == pytest.approx(a)
    # the transfer function reproduces the plant recursion from zero initial voltage
    plant.reset(0.0)
    i2 = P.sps_output_current(V1, N, F, L, PHI_NOM)
    sim = [plant.step(PHI_NOM)["v2"] for _ in range(50)]
    lin = z.simulate(np.full(51, i2))[1:]
    np.testing.assert_allclose(sim, lin, rtol=1e-12)
    no_load = plant.output_port_tf(None)
    np.testing.assert_allclose(no_load.num, [0.0, 10e-6 / 400e-6])
    np.testing.assert_allclose(no_load.den, [1.0, -1.0])
    assert no_load.dc_gain() == math.inf
    assert isinstance(z, ZTransfer)
    assert P.DabSpsPlantParameters().i2_max == pytest.approx(N * V1 / (8 * F * L))


def test_cross_check_with_design_agent_analytic_model():
    """Compare with AIPE-Design-Agent pea/converters/dab_sps.py when the sibling repository is present (stdlib-only module)."""
    candidates = [Path(__file__).resolve().parents[2] / "AIPE-Design-Agent" / "pea" / "converters" / "dab_sps.py",
                  Path("D:/Cursor Workspace/AIPE-Full-Ecosystem-Integration/repos/AIPE-Design-Agent/pea/converters/dab_sps.py")]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        pytest.skip("AIPE-Design-Agent dab_sps.py not available")
    spec = importlib.util.spec_from_file_location("dab_sps_reference", path)
    ref = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ref  # dataclasses resolve the module through sys.modules during class creation
    try:
        spec.loader.exec_module(ref)
    finally:
        sys.modules.pop(spec.name, None)
    for phi_deg, v2 in ((22.5, 400.0), (-22.5, 400.0), (10.0, 350.0), (35.0, 450.0), (-45.0, 380.0), (60.0, 400.0)):
        phi = math.radians(phi_deg)
        op = ref.SpsOperatingPoint(V1, v2, N, F, L, phi)
        assert P.sps_power(V1, v2, N, F, L, phi) == pytest.approx(ref.power(V1, v2, N, F, L, phi), rel=1e-12)
        assert P.sps_max_power(V1, v2, N, F, L) == pytest.approx(ref.max_power(V1, v2, N, F, L), rel=1e-12)
        assert P.series_current_rms(V1, v2, N, F, L, phi) == pytest.approx(ref.current_rms(op), rel=1e-12)
        assert P.series_current_peak(V1, v2, N, F, L, phi) == pytest.approx(ref.current_peak(op), rel=1e-12)
        for tk in np.linspace(0.0, T, 41):
            assert P.series_current_at(V1, v2, N, F, L, phi, tk, "centre") == pytest.approx(ref.current_at(op, tk, "centre"), abs=1e-9)
            assert P.series_current_at(V1, v2, N, F, L, phi, tk, "rising_edge") == pytest.approx(ref.current_at(op, tk, "rising_edge"), abs=1e-9)
        if phi_deg > 0:
            p = ref.power(V1, v2, N, F, L, phi)
            assert P.phase_shift_for_power(V1, v2, N, F, L, p) == pytest.approx(ref.phase_shift_for_power(V1, v2, N, F, L, p), rel=1e-12)
