"""End-to-end DAB experiments executed with a real ngspice (pytest marker: solver).

Skipped when no ngspice executable can be located. ``AIPE_TOOLS_DIR`` defaults to
the workspace tools directory so that ``tools/Spice64/bin/ngspice_con.exe`` is
found on the development machine without further configuration.
"""

from __future__ import annotations

import hashlib
import json
import os

os.environ.setdefault("AIPE_TOOLS_DIR", "D:/Cursor Workspace/AIPE-Full-Ecosystem-Integration/tools")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from aipe_simulation.dab.gating import SWITCHES  # noqa: E402
from aipe_simulation.dab.run import DabRunResult, reanalyse, run_dab  # noqa: E402
from aipe_simulation.dab.spec import DabCircuitSpec  # noqa: E402
from aipe_simulation.ngspice.locate import locate_ngspice, qualify_ngspice  # noqa: E402
from aipe_simulation.ngspice.runner import sha256_text  # noqa: E402
from aipe_simulation.waveforms.dataset import WaveformDataset  # noqa: E402

pytestmark = pytest.mark.solver

I_L0 = 14.285714285714288  # analytic i_L at the centre of the primary positive half-cycle, 10 kW point
P_NOMINAL = 10000.0
T = 1e-5
RUN_FILES = ("spec.json", "metadata.json", "circuit.cir", "circuit.log", "circuit.raw", "waveforms.h5", "summary.json", "run.json")


def rel_err(actual: float, expected: float) -> float:
    return abs(actual - expected) / abs(expected)


def nominal_spec(**overrides) -> DabCircuitSpec:
    spec = DabCircuitSpec(**overrides)
    spec.sim.use_initial_conditions = True
    spec.sim.initial_series_current = I_L0
    spec.sim.cycles = 12
    spec.sim.max_step_fraction = 200
    return spec


@pytest.fixture(scope="module")
def ngspice():
    info = locate_ngspice()
    if info is None:
        pytest.skip("ngspice not found (set AIPE_NGSPICE or AIPE_TOOLS_DIR)")
    return info


@pytest.fixture(scope="module")
def nominal_run(ngspice, tmp_path_factory) -> DabRunResult:
    return run_dab(nominal_spec(), tmp_path_factory.mktemp("dab_nominal"), ngspice=ngspice)


def test_qualify_ngspice_passes(ngspice, tmp_path):
    info = qualify_ngspice(ngspice, tmp_path)
    assert info.qualified is True
    q = info.qualification
    assert q["passed"] is True and q["returncode"] == 0
    assert set(q["measured"]) == {"v_1tau", "v_3tau"}
    assert all(err <= q["tolerance"] for err in q["relative_errors"].values())
    assert (tmp_path / "rc_smoke.cir").is_file() and (tmp_path / "rc_smoke.log").is_file()
    assert info.version not in ("", "unknown")


def test_nominal_run_matches_analytic_operating_point(nominal_run):
    r = nominal_run
    assert r.succeeded is True
    assert r.valid is True, r.messages
    assert r.status == "steady_state" and r.messages == []
    s = r.summary
    ss = s["steady_state"]
    assert ss["ok"] is True and ss["cycles_in_window"] == 4
    assert ss["t1"] == pytest.approx(12 * T, rel=1e-9)
    assert ss["t0"] == pytest.approx(8 * T, rel=1e-9)
    ports = s["ports"]
    assert ports["power_flow_direction"] == "port1_to_port2"
    assert rel_err(ports["port2"]["power_avg"]["value"], P_NOMINAL) < 5e-3
    assert rel_err(ports["port1"]["current_avg"]["value"], 12.5) < 5e-3
    assert rel_err(ports["port2"]["current_avg"]["value"], 25.0) < 5e-3
    assert ports["port1"]["voltage_avg"]["value"] == pytest.approx(800.0, rel=1e-9)
    assert ports["port2"]["voltage_avg"]["value"] == pytest.approx(400.0, rel=1e-9)
    assert ports["loss_total"]["value"] > 0.0
    assert 0.99 < ports["efficiency"]["value"] < 1.0
    assert rel_err(s["series_path"]["i_L_rms"]["value"], 13.6775) < 5e-3
    assert s["series_path"]["i_L_rms"]["unit"] == "A"
    phase = s["bridges"]["measured_phase_shift"]
    assert phase["available"] is True
    assert abs(phase["phi_deg_mean"]["value"] - 22.5) < 0.05
    switches = s["switches"]
    assert [sw["id"] for sw in switches] == list(SWITCHES)
    for sw in switches:
        assert sw["zvs_current_condition"]["all_events_met"] is True, sw["id"]
        assert sw["turn_off_events"] > 0 and sw["turn_on_events"] > 0
        assert sw["conduction_fraction"]["value"] > 0.3
    assert all(s["zvs_overview"][sw] is True for sw in SWITCHES)
    assert s["symmetry"]["i_L_periodicity_error"]["value"] < 1e-3
    assert abs(s["energy_balance"]["relative_unaccounted"]["value"]) < 1e-3
    assert s["spec_sha256"] == r.spec_sha256
    assert s["numerical"]["timestep"]["n_points"] > 1000


def test_run_directory_contents_and_hash_chain(nominal_run, ngspice):
    run_dir = Path(nominal_run.run_dir)
    for name in RUN_FILES:
        assert (run_dir / name).is_file(), name
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    netlist_bytes = (run_dir / "circuit.cir").read_bytes()
    netlist_text = netlist_bytes.decode("utf-8")
    assert run_json["run"]["netlist_sha256"] == sha256_text(netlist_text)
    assert run_json["run"]["netlist_sha256"] == hashlib.sha256(netlist_bytes).hexdigest()
    assert run_json["run"]["returncode"] == 0 and run_json["succeeded"] is True and run_json["valid"] is True
    assert run_json["run"]["ngspice_version"] == ngspice.version
    assert run_json["run"]["n_points"] > 1000
    spec_on_disk = DabCircuitSpec.from_dict(json.loads((run_dir / "spec.json").read_text(encoding="utf-8")))
    assert spec_on_disk == nominal_spec()
    assert run_json["spec_sha256"] == spec_on_disk.sha256() == nominal_run.spec_sha256
    assert f"* spec_sha256={nominal_run.spec_sha256}" in netlist_text
    assert "IC=14.2857142857" in netlist_text
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["spec_sha256"] == nominal_run.spec_sha256
    dataset = WaveformDataset.load_hdf5(run_dir / "waveforms.h5")
    assert dataset.sha256() == run_json["dataset_sha256"] == run_json["run"]["dataset_sha256"] == nominal_run.dataset_sha256
    assert dataset.metadata["netlist_sha256"] == run_json["run"]["netlist_sha256"]
    for channel in ("i_L", "v_ab", "v_cd", "i_dc1", "i_dc2", *[f"i_{s}" for s in SWITCHES], *[f"g_{s}" for s in SWITCHES]):
        assert channel in dataset, channel
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["valid"] is True
    assert summary["run"]["netlist_sha256"] == run_json["run"]["netlist_sha256"]
    assert summary["dataset_sha256"] == dataset.sha256()


def test_reanalyse_reproduces_valid_summary(nominal_run):
    summary = reanalyse(nominal_run.run_dir)
    assert summary["valid"] is True
    assert summary["status"] == "steady_state"
    original = nominal_run.summary
    assert summary["ports"]["port2"]["power_avg"]["value"] == pytest.approx(original["ports"]["port2"]["power_avg"]["value"], rel=1e-12)
    assert summary["series_path"]["i_L_rms"]["value"] == pytest.approx(original["series_path"]["i_L_rms"]["value"], rel=1e-12)
    on_disk = json.loads((Path(nominal_run.run_dir) / "summary.json").read_text(encoding="utf-8"))
    assert on_disk["valid"] is True


def test_reverse_power_flow(ngspice, tmp_path):
    spec = nominal_spec(phi_deg=-22.5)
    spec.sim.initial_series_current = -I_L0
    r = run_dab(spec, tmp_path, ngspice=ngspice)
    assert r.succeeded is True
    assert r.valid is True, r.messages
    ports = r.summary["ports"]
    assert ports["power_flow_direction"] == "port2_to_port1"
    assert rel_err(ports["port2"]["power_avg"]["value"], -P_NOMINAL) < 5e-3
    assert rel_err(ports["port1"]["power_avg"]["value"], -P_NOMINAL) < 5e-3
    assert rel_err(ports["port2"]["current_avg"]["value"], -25.0) < 5e-3
    assert abs(r.summary["bridges"]["measured_phase_shift"]["phi_deg_mean"]["value"] + 22.5) < 0.05
    assert all(r.summary["zvs_overview"][sw] is True for sw in SWITCHES)


def test_zero_initial_condition_run_reaches_steady_state(ngspice, tmp_path):
    spec = DabCircuitSpec(r_series_p=0.2)
    spec.sim.cycles = 60
    r = run_dab(spec, tmp_path, ngspice=ngspice)
    assert r.succeeded is True
    assert r.valid is True, r.messages
    assert rel_err(r.summary["ports"]["port1"]["power_avg"]["value"], P_NOMINAL) < 1e-2
    assert r.summary["ports"]["power_flow_direction"] == "port1_to_port2"
    ss = r.summary["steady_state"]
    assert ss["t1"] == pytest.approx(60 * T, rel=1e-9)
    assert ss["converged_from_cycle"] >= 1  # a start-up transient was observed before convergence
    cycles = [c["cycle"] for c in ss["per_cycle_metric"]]
    # ngspice writes its first raw point at t = tmax/100 rather than t = 0, so cycle 0 is
    # (marginally) incomplete and only cycles 1..59 count as complete cycles.
    assert cycles[-1] == 59 and cycles[0] <= 1
    assert cycles == list(range(cycles[0], 60))
    assert ss["cycles_available"] == len(cycles)
    per_cycle = [c["value"] for c in ss["per_cycle_metric"]]
    assert abs(per_cycle[0] - per_cycle[-1]) / per_cycle[-1] > 1e-2
    netlist = (tmp_path / "circuit.cir").read_text(encoding="utf-8")
    lext = next(line for line in netlist.splitlines() if line.startswith("Lext "))
    assert "IC=" not in lext
