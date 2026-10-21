"""DAB specification validation/serialisation and ngspice netlist generation (no solver needed)."""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from aipe_simulation.dab.netlist import SAVED_VECTORS, build_dab_netlist, netlist_metadata, saved_vectors, switch_table
from aipe_simulation.dab.spec import DabCircuitSpec, DcLinkModel, PortModel, SimulationSettings, SwitchModel

I_L0 = 14.285714285714288  # analytic i_L(0) at the nominal 10 kW operating point


def element_lines(netlist: str) -> dict[str, str]:
    """Map element name -> full line for every non-comment, non-dot line (SPICE names are unique)."""
    out: dict[str, str] = {}
    for line in netlist.splitlines():
        if line and not line.startswith(("*", ".")):
            name = line.split()[0]
            assert name not in out, f"duplicate element {name}"
            out[name] = line
    return out


def dot_lines(netlist: str, card: str) -> list[str]:
    return [line for line in netlist.splitlines() if line.startswith(card)]


def ic_value(line: str) -> float:
    match = re.search(r"\bIC=(\S+)", line)
    assert match, line
    return float(match.group(1))


# ---------------------------------------------------------------------------
# specification
# ---------------------------------------------------------------------------
def test_default_spec_is_valid_and_derived_quantities():
    spec = DabCircuitSpec()
    assert spec.validate() == []
    assert spec.period == pytest.approx(1e-5)
    assert spec.phi_rad == pytest.approx(22.5 / 180 * 3.141592653589793)
    assert spec.t_phi == pytest.approx(6.25e-7)
    assert spec.l_total_primary == pytest.approx(35e-6)
    assert spec.v2_referred == pytest.approx(800.0)
    assert spec.periodic_magnetising_current_at_origin == pytest.approx(-0.5)
    assert spec.t_max == pytest.approx(2.5e-8)
    assert spec.t_stop == pytest.approx(2.4e-4)
    assert spec.t_output_start == 0.0


def _set_level3(s):
    s.level = 3


def _set_phi120(s):
    s.phi_deg = 120.0


def _set_level1_dead_time(s):
    s.dead_time = 100e-9


def _set_negative_dead_time(s):
    s.dead_time = -1e-9


def _set_rc_load_without_capacitance(s):
    s.port2 = PortModel(type="rc_load", load_resistance=16.0)


def _set_tiny_snubber(s):
    s.switch.snubber_c = 1e-12
    s.switch.snubber_r = 1.0


def _set_zero_v1(s):
    s.v1 = 0.0


def _set_one_cycle(s):
    s.sim.cycles = 1


def _set_coarse_step(s):
    s.sim.max_step_fraction = 20


def _set_bad_method(s):
    s.sim.method = "euler"


def _set_port1_rc_load(s):
    s.port1 = PortModel(type="rc_load", capacitance=1e-4, load_resistance=64.0)


def _set_bad_port_type(s):
    s.port2 = PortModel(type="battery")


def _set_huge_dead_time(s):
    s.level = 2
    s.dead_time = 3e-6


def _set_zero_inductance(s):
    s.l_ext = 0.0


@pytest.mark.parametrize("mutate, expected", [
    (_set_level3, "level must be 1 or 2"),
    (_set_phi120, "phi_deg must lie within [-90, 90]"),
    (_set_level1_dead_time, "level 1 is the ideal reference: dead_time and c_oss must be zero"),
    (_set_negative_dead_time, "dead_time must be non-negative and smaller than a quarter period"),
    (_set_rc_load_without_capacitance, "port2 rc_load needs positive capacitance and load_resistance"),
    (_set_tiny_snubber, "numerical snubber time constant R*C must be at least 0.1 ns"),
    (_set_zero_v1, "v1 must be positive"),
    (_set_one_cycle, "sim.cycles must be at least 2"),
    (_set_coarse_step, "sim.max_step_fraction below 50"),
    (_set_bad_method, "sim.method must be gear or trap"),
    (_set_port1_rc_load, "port1 must be a voltage_source"),
    (_set_bad_port_type, "port2.type must be voltage_source or rc_load"),
    (_set_huge_dead_time, "dead_time must be non-negative and smaller than a quarter period"),
    (_set_zero_inductance, "total series inductance must be positive"),
], ids=lambda v: getattr(v, "__name__", None))
def test_invalid_specs_report_the_expected_problem(mutate, expected):
    spec = DabCircuitSpec()
    mutate(spec)
    problems = spec.validate()
    assert any(expected in p for p in problems), problems


def test_negative_dead_time_does_not_trigger_the_level_1_problem():
    spec = DabCircuitSpec()
    spec.dead_time = -1e-9
    problems = spec.validate()
    assert len(problems) == 1
    assert problems[0].startswith("dead_time must be non-negative")


def test_level_2_allows_dead_time_and_coss():
    spec = DabCircuitSpec(level=2, dead_time=100e-9)
    spec.switch.c_oss = 200e-12
    assert spec.validate() == []


def test_build_netlist_rejects_invalid_spec():
    with pytest.raises(ValueError, match="invalid DAB specification.*level must be 1 or 2"):
        build_dab_netlist(DabCircuitSpec(level=3))


def test_from_dict_round_trip():
    spec = DabCircuitSpec(name="rt", level=2, phi_deg=30.0, dead_time=100e-9, l_lk_p=1e-6, notes=["a note"])
    spec.sim.initial_series_current = 3.0
    spec.sim.cycles = 7
    spec.port2 = PortModel(type="rc_load", capacitance=100e-6, esr=1e-3, esl=1e-9, load_resistance=16.0, initial_voltage=410.0)
    spec.dc_link1 = DcLinkModel(capacitance=50e-6, esr=2e-3)
    data = spec.to_dict()
    for key in ("switch", "port1", "port2", "dc_link1", "dc_link2", "sim"):
        assert isinstance(data[key], dict)
    back = DabCircuitSpec.from_dict(data)
    assert back == spec
    assert back.to_dict() == data
    assert back.sha256() == spec.sha256()
    assert isinstance(back.sim, SimulationSettings) and isinstance(back.switch, SwitchModel)
    via_json = DabCircuitSpec.from_dict(json.loads(json.dumps(data)))
    assert via_json == spec
    partial = DabCircuitSpec.from_dict({"phi_deg": 10.0, "sim": {"cycles": 5}})
    assert partial.phi_deg == 10.0 and partial.sim.cycles == 5
    assert partial.v1 == 800.0 and partial.sim.max_step_fraction == 400


@pytest.mark.parametrize("data, message", [
    ({"foo": 1}, "unknown DabCircuitSpec fields"),
    ({"sim": {"bar": 2}}, "unknown sim fields"),
    ({"switch": {"r_onn": 1e-3}}, "unknown switch fields"),
    ({"port2": {"capacitence": 1e-4}}, "unknown port2 fields"),
])
def test_from_dict_rejects_unknown_keys(data, message):
    with pytest.raises(ValueError, match=message):
        DabCircuitSpec.from_dict(data)


def test_sha256_is_stable_and_sensitive_to_every_field():
    a, b = DabCircuitSpec(), DabCircuitSpec()
    assert a.sha256() == b.sha256()
    assert len(a.sha256()) == 64 and int(a.sha256(), 16) >= 0
    assert a.sha256() == hashlib.sha256(a.canonical_json().encode("utf-8")).hexdigest()
    assert a.sha256() == DabCircuitSpec.from_dict(a.to_dict()).sha256()
    canonical = a.canonical_json()
    assert ": " not in canonical and ", " not in canonical  # compact separators
    assert json.loads(canonical) == a.to_dict()
    assert list(json.loads(canonical)) == sorted(json.loads(canonical))  # sorted keys
    changed_top = DabCircuitSpec(phi_deg=22.6)
    changed_nested = DabCircuitSpec()
    changed_nested.sim.cycles = 25
    changed_switch = DabCircuitSpec()
    changed_switch.switch.r_on = 2e-3
    changed_notes = DabCircuitSpec(notes=["x"])
    hashes = {a.sha256(), changed_top.sha256(), changed_nested.sha256(), changed_switch.sha256(), changed_notes.sha256()}
    assert len(hashes) == 5


# ---------------------------------------------------------------------------
# netlist
# ---------------------------------------------------------------------------
def test_default_netlist_structure():
    spec = DabCircuitSpec()
    netlist = build_dab_netlist(spec)
    el = element_lines(netlist)
    for k in range(1, 9):
        assert el[f"S{k}"].endswith(" swmod"), el[f"S{k}"]
        assert el[f"S{k}"].split()[3] == f"g{k}"  # controlled by its own gate node
        assert el[f"Vg{k}"].startswith(f"Vg{k} g{k} 0 PULSE(")
        assert el[f"D{k}"].endswith(" dmod")
        assert el[f"VsS{k}"].endswith(" DC 0")
    assert el["Lext"] == "Lext a x1 3.5e-05"
    assert el["Lm"] == "Lm tp b 0.001 IC=0"
    assert el["Esec"] == "Esec ts0 d tp b 0.5"
    assert el["Fpri"] == "Fpri tp b Vis 0.5"
    assert el["Vis"] == "Vis ts0 ts DC 0"
    assert el["V1"] == "V1 p_pos 0 DC 800"
    assert el["V2"] == "V2 s_pos 0 DC 400"
    assert el["Rsp"] == "Rsp x1 x2 0.02"
    assert el["Vlkp"] == "Vlkp x2 tp DC 0" and el["Vlks"] == "Vlks ts x3 DC 0"
    assert "Llkp" not in el and "Llks" not in el
    tran = dot_lines(netlist, ".tran")
    assert tran == [".tran 2.5e-08 0.00024 0 2.5e-08 uic"]
    assert " uic" in tran[0]
    save = dot_lines(netlist, ".save")
    assert len(save) == 1
    assert save[0].split()[1:] == SAVED_VECTORS
    assert dot_lines(netlist, ".model swmod SW(") and dot_lines(netlist, ".model dmod D(")
    assert any("method=gear maxord=2" in line for line in dot_lines(netlist, ".options"))
    assert netlist.endswith(".end\n") and dot_lines(netlist, ".end") == [".end"]
    assert f"* spec_sha256={spec.sha256()}" in netlist
    assert "* spec_json=" + spec.canonical_json() in netlist
    # IC= only on the magnetising inductance when no initial series current is requested.
    assert [name for name, line in el.items() if "IC=" in line] == ["Lm"]
    assert not any(name.startswith(("Csn", "Rsn", "Coss")) for name in el)
    assert build_dab_netlist(spec) == netlist  # deterministic


def test_initial_conditions_on_series_and_magnetising_inductance():
    spec = DabCircuitSpec()
    spec.sim.use_initial_conditions = True
    spec.sim.initial_series_current = I_L0
    el = element_lines(build_dab_netlist(spec))
    assert re.fullmatch(r"Lext a x1 3\.5e-05 IC=\S+", el["Lext"])
    assert ic_value(el["Lext"]) == pytest.approx(I_L0, rel=1e-10)
    assert ic_value(el["Lm"]) == pytest.approx(spec.periodic_magnetising_current_at_origin, rel=1e-10)
    assert ic_value(el["Lm"]) == pytest.approx(-0.5)
    assert sorted(name for name, line in el.items() if "IC=" in line) == ["Lext", "Lm"]
    # explicit magnetising current overrides the periodic value
    spec.sim.initial_magnetising_current = 0.123
    el = element_lines(build_dab_netlist(spec))
    assert ic_value(el["Lm"]) == pytest.approx(0.123)
    # explicit magnetising current without a series current: Lext has no IC
    spec2 = DabCircuitSpec()
    spec2.sim.initial_magnetising_current = -0.25
    el2 = element_lines(build_dab_netlist(spec2))
    assert "IC=" not in el2["Lext"]
    assert ic_value(el2["Lm"]) == pytest.approx(-0.25)
    # reverse power flow: the periodic magnetising current changes sign with phi
    spec3 = DabCircuitSpec(phi_deg=-22.5)
    spec3.sim.initial_series_current = -I_L0
    el3 = element_lines(build_dab_netlist(spec3))
    assert ic_value(el3["Lm"]) == pytest.approx(0.5)
    assert ic_value(el3["Lext"]) == pytest.approx(-I_L0, rel=1e-10)


def test_snubber_and_coss_elements_only_when_enabled():
    spec = DabCircuitSpec()
    spec.switch.snubber_c = 1e-9
    spec.switch.snubber_r = 100.0
    el = element_lines(build_dab_netlist(spec))
    for k in range(1, 9):
        assert el[f"Csn{k}"].split()[1:] == [f"p_pos_s{k}" if k in (1, 3) else f"s_pos_s{k}" if k in (5, 7) else el[f"Csn{k}"].split()[1], f"sn{k}", "1e-09"]
        assert el[f"Rsn{k}"].split()[2:] == [f"sn{k}", "100"] or el[f"Rsn{k}"].split()[-1] == "100"
        assert el[f"Rsn{k}"].split()[1] == f"sn{k}"
    el_default = element_lines(build_dab_netlist(DabCircuitSpec()))
    assert not any(name.startswith(("Csn", "Rsn")) for name in el_default)
    level2 = DabCircuitSpec(level=2)
    level2.switch.c_oss = 150e-12
    el2 = element_lines(build_dab_netlist(level2))
    assert [el2[f"Coss{k}"].split()[-1] for k in range(1, 9)] == ["1.5e-10"] * 8
    assert not any(name.startswith("Coss") for name in el_default)


def test_rc_load_port_writes_capacitor_load_and_zero_volt_sense_source():
    spec = DabCircuitSpec()
    spec.port2 = PortModel(type="rc_load", capacitance=100e-6, esr=5e-3, load_resistance=16.0)
    assert spec.validate() == []
    netlist = build_dab_netlist(spec)
    el = element_lines(netlist)
    # Chain s_pos -> ESR -> (ESL only when > 0) -> C -> 0; the capacitor is pre-charged to v2 when initial_voltage is None.
    assert el["Resr2"] == "Resr2 s_pos c2x 0.005"
    assert el["C2"] == "C2 c2x 0 0.0001 IC=400"
    assert "Lesl2" not in el  # zero-valued parasitics are omitted, never emitted as placeholders
    assert el["Rload2"] == "Rload2 s_pos ld2 16"
    assert el["V2"] == "V2 ld2 0 DC 0"
    assert "Rload2 s_pos 0" not in netlist
    assert "Cdc2" not in el  # dc_link2 applies to the voltage_source port only
    spec.port2.initial_voltage = 380.0
    assert element_lines(build_dab_netlist(spec))["C2"] == "C2 c2x 0 0.0001 IC=380"
    spec.port2.esl = 20e-9
    el = element_lines(build_dab_netlist(spec))
    assert el["Lesl2"] == "Lesl2 c2x c2y 2e-08" and el["Resld2"].startswith("Resld2 c2x c2y ")
    assert el["C2"] == "C2 c2y 0 0.0001 IC=380"


def test_dc_link_and_leakage_elements():
    spec = DabCircuitSpec(l_ext=30e-6, l_lk_p=2e-6, l_lk_s=1e-6)
    spec.dc_link1 = DcLinkModel(capacitance=50e-6, esr=2e-3, source_resistance=0.1)
    spec.dc_link2 = DcLinkModel(capacitance=20e-6)
    el = element_lines(build_dab_netlist(spec))
    assert el["V1"] == "V1 src1 0 DC 800"
    assert el["Rsrc1"] == "Rsrc1 src1 src1b 0.1"
    assert el["Vsrc1"] == "Vsrc1 src1b p_pos DC 0"  # no source inductance -> direct (0 V) connection
    assert el["Resr1"] == "Resr1 p_pos cdc1x 0.002"
    assert el["Cdc1"] == "Cdc1 cdc1x 0 5e-05 IC=800"  # link capacitor pre-charged to the bus voltage
    assert "Lesl1" not in el and "Lsrc1" not in el
    assert el["Cdc2"] == "Cdc2 s_pos 0 2e-05 IC=400"
    assert el["Llkp"] == "Llkp x2 tp 2e-06" and el["Llks"] == "Llks ts x3 1e-06"
    assert "Vlkp" not in el and "Vlks" not in el


def test_netlist_metadata():
    spec = DabCircuitSpec(l_ext=30e-6, l_lk_p=2e-6, l_lk_s=1e-6, n_ratio=2.0)
    md = netlist_metadata(spec)
    assert md["l_total_primary_H"] == pytest.approx(30e-6 + 2e-6 + 2.0 ** 2 * 1e-6)
    assert md["l_total_primary_H"] == spec.l_total_primary
    assert md["v2_referred_V"] == pytest.approx(800.0)
    assert md["spec_sha256"] == spec.sha256()
    assert md["spec"] == spec.to_dict()
    assert md["saved_vectors"] == SAVED_VECTORS == saved_vectors()
    assert md["saved_vectors"] is not SAVED_VECTORS  # a copy
    assert md["t_max_s"] == spec.t_max and md["t_stop_s"] == spec.t_stop and md["t_output_start_s"] == 0.0
    switches = md["switches"]
    assert switches == switch_table()
    assert [s["id"] for s in switches] == [f"S{k}" for k in range(1, 9)]
    for s in switches:
        assert s["current_vector"] == f"i(Vs{s['id']})" and s["gate_vector"] == f"v(g{s['id'][1]})"
        assert s["current_vector"] in SAVED_VECTORS and s["gate_vector"] in SAVED_VECTORS
    assert len(md["timing"]["switch_roles"]) == 8
    assert md["timing"]["phi_deg"] == pytest.approx(22.5)
    json.dumps(md)
