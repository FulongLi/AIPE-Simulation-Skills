"""Single-phase-shift gate timing invariants for the eight DAB switches."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from aipe_simulation.dab.gating import HIGH_SIDE, LEG_OF, PRIMARY, SWITCHES, PulseSpec, SpsTiming

F_SW = 100e3
T = 1.0 / F_SW
VG = 15.0
TE = 10e-9
CASES = [(0.0, 0.0), (22.5, 0.0), (22.5, 100e-9), (-22.5, 100e-9), (-45.0, 50e-9), (60.0, 200e-9), (90.0, 100e-9)]
COMPLEMENTARY = (("S1", "S2"), ("S3", "S4"), ("S5", "S6"), ("S7", "S8"))
ATOL = 1e-15  # absolute time tolerance (T = 10 us)


@pytest.fixture(params=CASES, ids=[f"phi{p:+g}deg_td{d * 1e9:g}ns" for p, d in CASES])
def case(request):
    return request.param


@pytest.fixture
def timing(case) -> SpsTiming:
    phi_deg, dead_time = case
    return SpsTiming(F_SW, math.radians(phi_deg), dead_time, gate_voltage=VG, edge_time=TE)


def gate_state(timing: SpsTiming, switch: str, t: np.ndarray) -> np.ndarray:
    """Periodic on/off state of a switch, excluding the edge instants themselves."""
    phase = (t - timing.on_start(switch)) % timing.period
    return (phase > 1e-15) & (phase < timing.on_duration - 1e-15)


def test_period_shift_and_on_duration(timing, case):
    phi_deg, dead_time = case
    assert timing.period == pytest.approx(T)
    assert timing.t_phi == pytest.approx(phi_deg / 360.0 * T, abs=ATOL)
    assert timing.on_duration == pytest.approx(T / 2 - dead_time, abs=ATOL)
    for s in SWITCHES:
        rising = timing.rising_edges(s, 5 * T)
        falling = timing.falling_edges(s, 6 * T)
        assert len(rising) == 5  # one turn-on per period
        for r in rising:
            following = [f for f in falling if f > r + ATOL]
            assert following and following[0] == pytest.approx(r + T / 2 - dead_time, abs=ATOL)


def test_complementary_switches_never_overlap_and_gap_equals_dead_time(timing, case):
    _, dead_time = case
    tt = np.linspace(-T, 5 * T, 600001)
    for high, low in COMPLEMENTARY:
        g_high, g_low = gate_state(timing, high, tt), gate_state(timing, low, tt)
        assert not np.any(g_high & g_low), f"{high}/{low} overlap"
        assert np.mean(~g_high & ~g_low) == pytest.approx(2 * dead_time / T, abs=1e-4)
        for off_switch, on_switch in ((high, low), (low, high)):
            for f in timing.falling_edges(off_switch, 5 * T):
                nxt = [r for r in timing.rising_edges(on_switch, 6 * T, -T) if r >= f - ATOL]
                assert nxt, f"no turn-on of {on_switch} after {off_switch} turns off at {f}"
                assert nxt[0] - f == pytest.approx(dead_time, abs=ATOL)


def test_diagonal_pairs_have_identical_gates(timing):
    for a, b in (("S1", "S4"), ("S2", "S3"), ("S5", "S8"), ("S6", "S7")):
        assert timing.on_start(a) == timing.on_start(b)
        assert timing.rising_edges(a, 5 * T) == timing.rising_edges(b, 5 * T)
        assert timing.falling_edges(a, 5 * T) == timing.falling_edges(b, 5 * T)
        assert timing.gate_pulse(a) == timing.gate_pulse(b)


def test_secondary_gates_are_primary_gates_shifted_by_t_phi(timing):
    shift = timing.t_phi
    for primary, secondary in (("S1", "S5"), ("S2", "S6"), ("S3", "S7"), ("S4", "S8")):
        assert timing.on_start(secondary) == pytest.approx(timing.on_start(primary) + shift, abs=ATOL)
        for edges in (timing.rising_edges, timing.falling_edges):
            prim = np.array(edges(primary, 5 * T, 0.0))
            sec = np.array(edges(secondary, 5 * T + shift, shift))
            assert prim.size == sec.size == 5
            np.testing.assert_allclose(sec, prim + shift, atol=ATOL, rtol=0)


def test_ideal_switching_instants(timing, case):
    _, dead_time = case
    primary = timing.ideal_switching_instants("primary", 3 * T)
    times = [e["t"] for e in primary]
    directions = [e["direction"] for e in primary]
    np.testing.assert_allclose(times, [T / 4 + k * T / 2 for k in range(6)], atol=ATOL, rtol=0)
    assert directions == [-1, +1, -1, +1, -1, +1]
    # Each instant is the centre of the leg-A dead band.
    s1_fall, s1_rise = timing.falling_edges("S1", 3 * T), timing.rising_edges("S1", 3 * T)
    s2_fall, s2_rise = timing.falling_edges("S2", 3 * T), timing.rising_edges("S2", 3 * T)
    for e in primary:
        if e["direction"] < 0:  # +V1 -> -V1: S1 off, then S2 on
            assert any(abs(f - (e["t"] - dead_time / 2)) <= ATOL for f in s1_fall)
            assert any(abs(r - (e["t"] + dead_time / 2)) <= ATOL for r in s2_rise)
        else:
            assert any(abs(f - (e["t"] - dead_time / 2)) <= ATOL for f in s2_fall)
            assert any(abs(r - (e["t"] + dead_time / 2)) <= ATOL for r in s1_rise)
    shift = timing.t_phi
    secondary = timing.ideal_switching_instants("secondary", 3 * T + shift, shift)
    np.testing.assert_allclose([e["t"] for e in secondary], np.array(times) + shift, atol=ATOL, rtol=0)
    assert [e["direction"] for e in secondary] == directions
    windowed = timing.ideal_switching_instants("primary", 2 * T, T)
    np.testing.assert_allclose([e["t"] for e in windowed], [5 * T / 4, 7 * T / 4], atol=ATOL, rtol=0)


def _numbers(spice: str) -> list[float]:
    assert spice.startswith("PULSE(") and spice.endswith(")")
    return [float(tok) for tok in spice[len("PULSE("):-1].split()]


def test_gate_pulse_strings_and_initial_levels(timing):
    for s in SWITCHES:
        pulse = timing.gate_pulse(s)
        assert isinstance(pulse, PulseSpec)
        text = pulse.spice()
        numbers = _numbers(text)
        assert len(numbers) == 7
        initially_on = bool(gate_state(timing, s, np.array([0.0]))[0])
        assert numbers[0] == (VG if initially_on else 0.0), (s, text)
        assert numbers[1] == (0.0 if initially_on else VG)
        assert numbers[3] == pytest.approx(TE) and numbers[4] == pytest.approx(TE)
        assert numbers[6] == pytest.approx(T, rel=1e-9)
        assert pulse.per == T and pulse.tr == TE and pulse.tf == TE
    # Time origin is the centre of the primary positive half-cycle: S1/S4 on, S2/S3 off.
    assert _numbers(timing.gate_pulse("S1").spice())[0] == VG
    assert _numbers(timing.gate_pulse("S4").spice())[0] == VG
    assert _numbers(timing.gate_pulse("S2").spice())[0] == 0.0
    assert _numbers(timing.gate_pulse("S3").spice())[0] == 0.0


def test_gate_pulse_edge_midpoints_match_timing(timing):
    for s in SWITCHES:
        p = timing.gate_pulse(s)
        r0 = timing.on_start(s) % T
        f0 = (timing.on_start(s) + timing.on_duration) % T
        assert min(r0, f0) >= TE / 2, "test cases must not need the t=0 clamp"
        first_mid = p.td + p.tr / 2
        second_mid = p.td + p.tr + p.pw + p.tf / 2
        if p.v_initial == 0.0:  # low -> high at r0, high -> low at f0
            assert first_mid == pytest.approx(r0, abs=1e-14)
            assert second_mid == pytest.approx(f0, abs=1e-14)
        else:  # high -> low at f0, low -> high at r0
            assert first_mid == pytest.approx(f0, abs=1e-14)
            assert second_mid == pytest.approx(r0, abs=1e-14)
        assert p.pw >= TE


def test_describe_lists_eight_switch_roles(timing, case):
    phi_deg, dead_time = case
    d = timing.describe()
    roles = d["switch_roles"]
    assert len(roles) == 8 and set(roles) == set(SWITCHES)
    for s, role in roles.items():
        assert role["leg"] == LEG_OF[s]
        assert role["side"] == ("high" if s in HIGH_SIDE else "low")
        assert role["bridge"] == ("primary" if s in PRIMARY else "secondary")
    assert [r["leg"] for r in roles.values()] == ["A", "A", "B", "B", "C", "C", "D", "D"]
    assert d["modulation"] == "single-phase-shift"
    assert d["phi_deg"] == pytest.approx(phi_deg)
    assert d["dead_time_s"] == dead_time
    assert d["on_duration_s"] == pytest.approx(T / 2 - dead_time)
    assert set(d["gate_pulses"]) == set(SWITCHES)
    assert all(v.startswith("PULSE(") for v in d["gate_pulses"].values())
    json.dumps(d)


def test_edge_window_boundaries():
    timing = SpsTiming(F_SW, 0.0)
    np.testing.assert_allclose(timing.rising_edges("S1", 3 * T), [0.75 * T, 1.75 * T, 2.75 * T], atol=ATOL, rtol=0)
    np.testing.assert_allclose(timing.rising_edges("S1", 3 * T, T), [1.75 * T, 2.75 * T], atol=ATOL, rtol=0)
    np.testing.assert_allclose(timing.rising_edges("S1", 0.75 * T), [0.75 * T], atol=ATOL, rtol=0)  # inclusive end
    np.testing.assert_allclose(timing.falling_edges("S1", T), [0.25 * T], atol=ATOL, rtol=0)
    assert timing.rising_edges("S1", 0.5 * T) == []
    np.testing.assert_allclose(timing.rising_edges("S2", T), [0.25 * T], atol=ATOL, rtol=0)
