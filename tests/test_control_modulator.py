"""Discrete SPS modulator: edge times versus SpsTiming, quantisation, limiting, slew, reversal, synchronisation."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from aipe_simulation.control.sps_modulator import POSITIVE_PATTERN, PhaseRegister, SpsModulator, SpsModulatorConfig
from aipe_simulation.dab.gating import PRIMARY, SWITCHES, SpsTiming

F_SW = 100e3
T = 1.0 / F_SW
TD = 200e-9
ATOL = 1e-15  # absolute time tolerance (T = 10 us)
PHI_CASES = [0.0, 10.0, 22.5, -22.5, 35.0, -45.0, 60.0]
COMPLEMENTARY = (("S1", "S2"), ("S3", "S4"), ("S5", "S6"), ("S7", "S8"))


def exact_config(**overrides) -> SpsModulatorConfig:
    base = dict(f_sw=F_SW, dead_time=TD, quantise=False, phi_max_rad=math.radians(80.0),
                slew_max_rad_per_update=math.radians(90.0))
    base.update(overrides)
    return SpsModulatorConfig(**base)


@pytest.mark.parametrize("phi_deg", PHI_CASES)
def test_edges_match_sps_timing_exactly(phi_deg):
    mod = SpsModulator(exact_config())
    applied = mod.command(math.radians(phi_deg))
    assert applied == pytest.approx(math.radians(phi_deg), abs=1e-15)
    timing = SpsTiming(F_SW, math.radians(phi_deg), TD)
    for s in SWITCHES:
        for name in ("rising_edges", "falling_edges"):
            ours = getattr(mod, name)(s, 5 * T, 0.0)
            ref = getattr(timing, name)(s, 5 * T, 0.0)
            assert len(ours) == len(ref) >= 5, (s, name)
            np.testing.assert_allclose(ours, ref, atol=ATOL, rtol=0)
    for bridge in ("primary", "secondary"):
        ours = mod.ideal_switching_instants(bridge, 3 * T, 0.0)
        ref = timing.ideal_switching_instants(bridge, 3 * T, 0.0)
        assert [e["direction"] for e in ours] == [e["direction"] for e in ref]
        np.testing.assert_allclose([e["t"] for e in ours], [e["t"] for e in ref], atol=ATOL, rtol=0)
    equivalent = mod.timing()
    assert equivalent.phi_rad == pytest.approx(math.radians(phi_deg), abs=1e-15)
    assert equivalent.dead_time == TD and equivalent.f_sw == F_SW


@pytest.mark.parametrize("phi_deg", [22.5, -22.5, 10.0])
def test_delayed_turn_on_dead_band_shifts_gates_by_half_dead_time_only(phi_deg):
    centred = SpsModulator(exact_config())
    delayed = SpsModulator(exact_config(dead_band_mode="delayed_turn_on"))
    centred.command(math.radians(phi_deg))
    delayed.command(math.radians(phi_deg))
    for s in SWITCHES:
        np.testing.assert_allclose(delayed.rising_edges(s, 4 * T, T), np.array(centred.rising_edges(s, 4 * T - TD / 2, T - TD / 2)) + TD / 2, atol=ATOL, rtol=0)
        np.testing.assert_allclose(delayed.falling_edges(s, 4 * T, T), np.array(centred.falling_edges(s, 4 * T - TD / 2, T - TD / 2)) + TD / 2, atol=ATOL, rtol=0)
    # bridge-voltage transitions (phase shift) are not affected by the dead-band placement
    assert delayed.ideal_switching_instants("secondary", 3 * T) == centred.ideal_switching_instants("secondary", 3 * T)


def test_common_time_base_leg_to_leg_180_and_complementary_dead_band():
    mod = SpsModulator(exact_config())
    mod.command(math.radians(22.5))
    for a, b in (("S1", "S4"), ("S2", "S3"), ("S5", "S8"), ("S6", "S7")):
        assert mod.on_intervals(a, 0.0, 5 * T) == mod.on_intervals(b, 0.0, 5 * T)
    t = np.linspace(0.0, 5 * T, 500001)
    g = mod.gate_states(t)
    for high, low in COMPLEMENTARY:
        assert not np.any(g[high] & g[low])
        assert np.mean(~g[high] & ~g[low]) == pytest.approx(2 * TD / T, abs=2e-4)
        assert np.mean(g[high]) == pytest.approx((T / 2 - TD) / T, abs=2e-4)
    # time origin: centre of the primary positive half-cycle -> S1 and S4 on, S2 and S3 off
    at_zero = mod.gate_states(np.array([0.0]))
    assert at_zero["S1"][0] and at_zero["S4"][0] and not at_zero["S2"][0] and not at_zero["S3"][0]
    bridges = mod.bridge_states(t)
    assert set(np.unique(bridges["v_ab"])) <= {-1.0, 0.0, 1.0}
    assert np.mean(np.abs(bridges["v_ab"])) == pytest.approx(1 - 2 * TD / T, abs=2e-4)
    assert np.mean(bridges["v_ab"]) == pytest.approx(0.0, abs=2e-3)
    assert bridges["v_ab"][0] == 1.0


@pytest.mark.parametrize("phi_deg", [22.5, -22.5, 35.0, -10.0])
def test_secondary_shift_sign_convention_and_power_reversal(phi_deg):
    mod = SpsModulator(exact_config())
    mod.command(math.radians(phi_deg))
    t_phi = math.radians(phi_deg) / (2 * math.pi) * T
    prim = [e["t"] for e in mod.ideal_switching_instants("primary", 3 * T, 0.0)]
    sec = [e["t"] for e in mod.ideal_switching_instants("secondary", 3 * T + t_phi, t_phi)]
    np.testing.assert_allclose(sec, np.array(prim) + t_phi, atol=ATOL, rtol=0)
    assert math.copysign(1.0, t_phi) == (1.0 if phi_deg > 0 else -1.0)
    assert mod.register.direction == (1 if phi_deg > 0 else -1)
    assert mod.register.t_phi == pytest.approx(t_phi, abs=ATOL)
    for primary, secondary in (("S1", "S5"), ("S2", "S6"), ("S3", "S7"), ("S4", "S8")):
        np.testing.assert_allclose(mod.rising_edges(secondary, 4 * T + t_phi, T + t_phi),
                                   np.array(mod.rising_edges(primary, 4 * T, T)) + t_phi, atol=ATOL, rtol=0)


def test_quantisation_to_timer_grid():
    cfg = SpsModulatorConfig(f_sw=F_SW, pwm_clock_hz=100e6, hr_step_s=150e-12, dead_time=TD, slew_max_rad_per_update=math.radians(90))
    assert cfg.validate() == []
    assert cfg.tbprd == 500.0 and cfg.coarse_step == pytest.approx(10e-9)
    assert cfg.phase_resolution == 150e-12 and math.degrees(cfg.phase_resolution_rad) == pytest.approx(0.0054)
    assert cfg.dead_time_realised == pytest.approx(200e-9) and cfg.describe()["dead_time_counts"] == 20
    mod = SpsModulator(cfg)
    rng = np.random.default_rng(1)
    for phi in np.concatenate([rng.uniform(-math.pi / 4, math.pi / 4, 300), [0.0, math.radians(22.5), -math.radians(22.5)]]):
        reg = mod.quantise_phase(float(phi))
        assert isinstance(reg, PhaseRegister) and reg.quantised
        t_exact = phi / (2 * math.pi) * T
        assert abs(reg.t_phi - t_exact) <= cfg.hr_step_s * (0.5 + 1e-9) + 1e-18
        assert 0 <= reg.fine_steps <= math.floor(cfg.coarse_step / cfg.hr_step_s)
        reconstructed = reg.direction * (reg.coarse_counts * cfg.coarse_step + reg.fine_steps * cfg.hr_step_s)
        assert reconstructed == pytest.approx(reg.t_phi, abs=1e-18)
        assert reg.phi_rad == pytest.approx(reg.t_phi / T * 2 * math.pi, abs=1e-15)
        if phi == 0.0:
            assert reg.direction == 0 and reg.coarse_counts == 0 and reg.fine_steps == 0
    coarse_only = SpsModulator(SpsModulatorConfig(f_sw=F_SW, pwm_clock_hz=100e6, hr_step_s=None, dead_time=TD, slew_max_rad_per_update=math.radians(90)))
    for phi in rng.uniform(-math.pi / 4, math.pi / 4, 100):
        reg = coarse_only.quantise_phase(float(phi))
        assert reg.fine_steps == 0
        assert abs(reg.t_phi - phi / (2 * math.pi) * T) <= 5e-9 * (1 + 1e-9)
    # a quantised modulator reproduces SpsTiming of its realised phase exactly, and the ideal timing within one step
    phi_cmd = math.radians(22.5)
    applied = mod.command(phi_cmd)
    exact_timing = SpsTiming(F_SW, applied, cfg.dead_time_realised)
    ideal_timing = SpsTiming(F_SW, phi_cmd, TD)
    for s in SWITCHES:
        np.testing.assert_allclose(mod.rising_edges(s, 5 * T, 0.0), exact_timing.rising_edges(s, 5 * T, 0.0), atol=ATOL, rtol=0)
        tol = 0.0 if s in PRIMARY else cfg.hr_step_s
        np.testing.assert_allclose(mod.rising_edges(s, 5 * T, 0.0), ideal_timing.rising_edges(s, 5 * T, 0.0), atol=tol + 1e-18, rtol=0)
    # the nominal 22.5 deg (625 ns) is not on the 10 ns grid; it is reached with 62 coarse counts + 33 fine steps
    reg = mod.quantise_phase(phi_cmd)
    assert (reg.coarse_counts, reg.fine_steps) == (62, 33)
    assert abs(reg.t_phi - 625e-9) < 75e-12


def test_command_limit_and_slew_limit():
    cfg = SpsModulatorConfig(f_sw=F_SW, dead_time=TD, phi_max_rad=math.radians(45.0), slew_max_rad_per_update=math.radians(1.0), quantise=False)
    mod = SpsModulator(cfg)
    values = [math.degrees(mod.command(math.radians(60.0))) for _ in range(50)]
    assert values[0] == pytest.approx(1.0, abs=1e-9)  # ramps from zero at the slew limit
    np.testing.assert_allclose(np.diff(values[:45]), 1.0, atol=1e-9)
    assert max(values) == pytest.approx(45.0, abs=1e-9) and values[-1] == pytest.approx(45.0, abs=1e-9)
    assert mod.limited is True and mod.slew_limited is False
    down = [math.degrees(mod.command(math.radians(-60.0))) for _ in range(3)]
    np.testing.assert_allclose(down, [44.0, 43.0, 42.0], atol=1e-9)
    assert mod.slew_limited is True and mod.limited is True
    assert math.degrees(mod.phi_limited) == pytest.approx(42.0, abs=1e-9)  # pre-quantisation value for anti-windup feedback
    # with timer quantisation (150 ps = 0.0054 deg) the same ramp stays within one register step of the ideal values
    quantised = SpsModulator(SpsModulatorConfig(f_sw=F_SW, dead_time=TD, phi_max_rad=math.radians(45.0), slew_max_rad_per_update=math.radians(1.0)))
    qv = [math.degrees(quantised.command(math.radians(60.0))) for _ in range(50)]
    assert max(qv) <= 45.0 + 0.003 and qv[-1] == pytest.approx(45.0, abs=0.003)
    np.testing.assert_allclose(np.diff(qv[:45]), 1.0, atol=0.006)
    with pytest.raises(ValueError):
        mod.command(float("nan"))


def test_disable_turns_all_gates_off_and_restart_ramps_from_zero():
    mod = SpsModulator(SpsModulatorConfig(f_sw=F_SW, dead_time=TD, slew_max_rad_per_update=math.radians(90.0)))
    for _ in range(3):
        mod.command(math.radians(20.0))  # periods 0, 1, 2
    assert mod.command(math.radians(20.0), enable=False) == 0.0  # period 3 disabled (trip)
    assert mod.enabled is False and mod.phi_applied == 0.0 and mod.register.direction == 0
    assert mod.command(math.radians(20.0), enable=False) == 0.0  # period 4 disabled
    t_off = np.linspace(2.5 * T + 1e-12, 4.5 * T - 1e-12, 2001)  # periods 3 and 4: [2.5 T, 4.5 T)
    g = mod.gate_states(t_off)
    assert not any(g[s].any() for s in SWITCHES)
    # an on-interval that started in period 2 is cut at the period boundary 2.5 T
    s2 = mod.on_intervals("S2", 2 * T, 3 * T)
    assert any(abs(b - 2.5 * T) <= ATOL for _, b in s2)
    assert mod.ideal_switching_instants("primary", 4.5 * T, 2.5 * T) == []
    assert [e["enabled"] for e in mod.schedule()] == [True, True, True, False, False]
    # re-enable: the slew limiter restarts from zero
    slow = SpsModulator(SpsModulatorConfig(f_sw=F_SW, dead_time=TD, slew_max_rad_per_update=math.radians(1.0)))
    for _ in range(10):
        slow.command(math.radians(10.0))
    slow.command(0.0, enable=False)
    assert math.degrees(slow.command(math.radians(10.0))) == pytest.approx(1.0, abs=0.003)


def test_update_divider_holds_register_between_updates():
    mod = SpsModulator(SpsModulatorConfig(f_sw=F_SW, dead_time=TD, update_divider=4, slew_max_rad_per_update=math.radians(90.0)))
    applied = [math.degrees(mod.command(math.radians(v))) for v in (5.0, 10.0, 15.0, 20.0, 25.0, 30.0)]
    assert applied[0] == pytest.approx(5.0, abs=0.003)
    assert applied[1] == applied[2] == applied[3] == applied[0]
    assert applied[4] == pytest.approx(25.0, abs=0.003) and applied[5] == applied[4]


def test_phase_step_between_periods_keeps_on_times_positive_and_exact():
    mod = SpsModulator(exact_config())
    mod.command(math.radians(10.0))
    mod.command(math.radians(10.0))
    mod.command(math.radians(30.0))
    mod.command(math.radians(30.0))
    d_t = (math.radians(30.0) - math.radians(10.0)) / (2 * math.pi) * T
    for s in SWITCHES:
        for a, b in mod.on_intervals(s, 0.0, 4 * T):
            assert b - a > 0
    # secondary complement switch S6 spans the register update between periods 1 and 2: on-time grows by the phase step
    lengths = sorted(b - a for a, b in mod.on_intervals("S6", 0.5 * T, 2.5 * T))
    assert lengths[-1] == pytest.approx(T / 2 - TD + d_t, abs=ATOL)
    assert all(l == pytest.approx(T / 2 - TD, abs=ATOL) for l in lengths[:-1])
    # the secondary positive-pattern switch keeps its nominal on-time in every period
    for a, b in mod.on_intervals("S5", -0.5 * T, 3.5 * T):
        assert b - a == pytest.approx(T / 2 - TD, abs=ATOL)
    sec = mod.ideal_switching_instants("secondary", 3.5 * T, -0.5 * T)
    assert len(sec) == 8
    assert sec[2]["t"] - sec[0]["t"] == pytest.approx(T, abs=ATOL)  # before the step
    assert sec[6]["t"] - sec[4]["t"] == pytest.approx(T, abs=ATOL)  # after the step
    assert sec[4]["t"] - sec[2]["t"] == pytest.approx(T + d_t, abs=ATOL)  # one stretched period


@pytest.mark.parametrize("overrides, message", [
    (dict(pwm_clock_hz=100.05e6), "integer period register"),
    (dict(dead_time=3e-6), "quarter period"),
    (dict(phi_max_rad=math.pi / 2), "phi_max_rad must lie in (0, pi/2)"),
    (dict(slew_max_rad_per_update=math.radians(200.0), dead_time=0.0), "slew per update plus dead time"),
    (dict(hr_step_s=20e-9), "hr_step_s must be positive and smaller"),
    (dict(dead_band_mode="late"), "dead_band_mode"),
    (dict(update_divider=0), "update_divider"),
])
def test_invalid_configurations_are_rejected(overrides, message):
    cfg = SpsModulatorConfig(f_sw=F_SW, **overrides)
    problems = cfg.validate()
    assert any(message in p for p in problems), problems
    with pytest.raises(ValueError, match="invalid SPS modulator configuration"):
        SpsModulator(cfg)


def test_describe_is_json_serialisable_and_lists_roles():
    mod = SpsModulator()
    mod.command(math.radians(22.5))
    d = mod.describe()
    json.dumps(d)
    assert set(d["switch_roles"]) == set(SWITCHES)
    assert all(d["switch_roles"][s]["pattern"].startswith("positive") for s in POSITIVE_PATTERN)
    assert d["register"]["direction"] == 1 and d["enabled"] is True
    assert d["sign_convention"].startswith("phi > 0: secondary lags")
    assert d["tbprd_counts"] == 500.0
