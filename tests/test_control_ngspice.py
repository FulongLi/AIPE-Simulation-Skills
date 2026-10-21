"""Cycle-averaged control plant versus executed ngspice Level 1 runs (pytest marker: solver).

Skipped when no ngspice executable can be located. ``AIPE_TOOLS_DIR`` defaults to
the workspace tools directory so that ``tools/Spice64/bin/ngspice_con.exe`` is
found on the development machine without further configuration.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("AIPE_TOOLS_DIR", "D:/Cursor Workspace/AIPE-Full-Ecosystem-Integration/tools")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from aipe_simulation.control.plant import sps_power  # noqa: E402
from aipe_simulation.control.verify import compare_power_with_ngspice, format_comparison_table  # noqa: E402
from aipe_simulation.ngspice.locate import locate_ngspice  # noqa: E402

pytestmark = pytest.mark.solver

PHI_DEG = (10.0, 22.5, 35.0)
RUN_FILES = ("spec.json", "metadata.json", "circuit.cir", "circuit.log", "circuit.raw", "waveforms.h5", "summary.json", "run.json")


@pytest.fixture(scope="module")
def ngspice():
    info = locate_ngspice()
    if info is None:
        pytest.skip("ngspice not found (set AIPE_NGSPICE or AIPE_TOOLS_DIR)")
    return info


@pytest.fixture(scope="module")
def report(ngspice, tmp_path_factory):
    return compare_power_with_ngspice(PHI_DEG, tmp_path_factory.mktemp("plant_verification"), ngspice=ngspice)


def test_every_operating_point_reaches_periodic_steady_state(report):
    assert report["all_valid"] is True
    assert [r["phi_deg"] for r in report["rows"]] == list(PHI_DEG)
    for row in report["rows"]:
        assert row["succeeded"] is True and row["valid"] is True and row["status"] == "steady_state", row["messages"]
        assert row["steady_state_window_cycles"] == 4
        assert abs(row["phi_measured_deg"] - row["phi_deg"]) < 0.05


def test_plant_power_law_agrees_with_ngspice_within_half_percent(report):
    for row in report["rows"]:
        assert row["p_plant_W"] == pytest.approx(sps_power(800.0, 400.0, 2.0, 1e5, 35e-6, row["phi_deg"] * 3.141592653589793 / 180.0))
        assert abs(row["rel_err_p2"]) < 5e-3 and abs(row["rel_err_p1"]) < 5e-3
        assert row["rel_err_p2"] < 0.0  # Level 1 includes 20 mOhm series resistance and 1 mOhm Ron: output power below the lossless law
        assert abs(row["rel_err_i2"]) < 5e-3
        assert abs(row["rel_err_i_l_rms"]) < 2e-3
    assert report["max_abs_rel_err_p2"] < 5e-3 and report["max_abs_rel_err_p1"] < 5e-3
    nominal = next(r for r in report["rows"] if r["phi_deg"] == 22.5)
    assert nominal["p2_ngspice_W"] == pytest.approx(10000.0, rel=5e-3)
    assert nominal["i2_ngspice_A"] == pytest.approx(25.0, rel=5e-3)


def test_report_files_and_provenance(report, ngspice):
    assert report["ngspice"]["version"] == ngspice.version
    out = Path(report["report_path"]).parent
    assert (out / "plant_verification.json").is_file() and (out / "plant_verification.md").is_file()
    on_disk = json.loads((out / "plant_verification.json").read_text(encoding="utf-8"))
    assert on_disk["schema"] == "aipe-dab-sps-plant-verification/0.1"
    assert [r["phi_deg"] for r in on_disk["rows"]] == list(PHI_DEG)
    for row in report["rows"]:
        run_dir = Path(row["run_dir"])
        for name in RUN_FILES:
            assert (run_dir / name).is_file(), name
        assert len(row["netlist_sha256"]) == 64 and len(row["dataset_sha256"]) == 64
        netlist = (run_dir / "circuit.cir").read_text(encoding="utf-8")
        assert "IC=" in next(line for line in netlist.splitlines() if line.startswith("Lext "))
    table = format_comparison_table(report)
    assert table.count("steady_state") == len(PHI_DEG)
    assert (out / "plant_verification.md").read_text(encoding="utf-8") == table
