"""Command-line interface smoke tests (``python -m aipe_simulation.cli``)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from aipe_simulation import cli
from aipe_simulation.dab.netlist import build_dab_netlist
from aipe_simulation.dab.spec import DabCircuitSpec

REPO = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "aipe_simulation.cli", *args], capture_output=True, text=True,
                          cwd=str(REPO), timeout=180, env=env)


def test_default_spec_prints_yaml_with_f_sw():
    cp = run_cli("dab", "default-spec")
    assert cp.returncode == 0, cp.stderr
    assert "f_sw" in cp.stdout
    data = yaml.safe_load(cp.stdout)
    assert data["f_sw"] == 100000.0
    assert DabCircuitSpec.from_dict(data) == DabCircuitSpec()
    assert list(data)[:3] == ["name", "level", "v1"]  # field order preserved (sort_keys=False)


def test_netlist_without_spec_prints_default_netlist():
    cp = run_cli("dab", "netlist")
    assert cp.returncode == 0, cp.stderr
    assert ".end" in cp.stdout
    assert cp.stdout.rstrip().endswith(".end")
    assert ".tran" in cp.stdout and "Vg8 g8 0 PULSE(" in cp.stdout
    assert cp.stdout.replace("\r\n", "\n") == build_dab_netlist(DabCircuitSpec())


def test_help_exits_zero():
    cp = run_cli("--help")
    assert cp.returncode == 0
    assert "usage" in cp.stdout.lower() and "dab" in cp.stdout
    assert run_cli("dab", "--help").returncode == 0
    assert run_cli("dab", "netlist", "--help").returncode == 0


def test_no_command_is_a_usage_error():
    cp = run_cli()
    assert cp.returncode == 2
    assert "usage" in cp.stderr.lower()


def test_netlist_from_yaml_and_json_spec_files(tmp_path):
    spec = DabCircuitSpec(phi_deg=30.0, name="cli-spec")
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(yaml.safe_dump(spec.to_dict(), sort_keys=False), encoding="utf-8")
    out_path = tmp_path / "circuit.cir"
    cp = run_cli("dab", "netlist", "--spec", str(yaml_path), "--out", str(out_path))
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout == ""
    written = out_path.read_text(encoding="utf-8")
    assert written == build_dab_netlist(spec)
    assert f"* spec_sha256={spec.sha256()}" in written
    json_path = tmp_path / "spec.json"
    json_path.write_text(json.dumps(spec.to_dict()), encoding="utf-8")
    cp = run_cli("dab", "netlist", "--spec", str(json_path))
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.replace("\r\n", "\n") == build_dab_netlist(spec)


def test_invalid_spec_file_fails_with_message(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"level": 3}), encoding="utf-8")
    cp = run_cli("dab", "netlist", "--spec", str(path))
    assert cp.returncode != 0
    assert "invalid DAB specification" in cp.stderr


def test_main_in_process(capsys):
    assert cli.main(["dab", "default-spec"]) == 0
    out = capsys.readouterr().out
    assert "f_sw" in out and yaml.safe_load(out)["phi_deg"] == 22.5
    assert cli.main(["dab", "netlist"]) == 0
    assert capsys.readouterr().out.rstrip().endswith(".end")
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0


@pytest.mark.solver
def test_doctor_reports_qualified_solver(tmp_path):
    env = {**os.environ}
    env.setdefault("AIPE_TOOLS_DIR", "D:/Cursor Workspace/AIPE-Full-Ecosystem-Integration/tools")
    from aipe_simulation.ngspice.locate import locate_ngspice
    os.environ.setdefault("AIPE_TOOLS_DIR", env["AIPE_TOOLS_DIR"])
    if locate_ngspice() is None:
        pytest.skip("ngspice not found")
    cp = run_cli("doctor", "--workdir", str(tmp_path), env=env)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    report = json.loads(cp.stdout)
    assert report["ngspice"]["qualified"] is True
    assert report["ngspice"]["qualification"]["passed"] is True
    assert (tmp_path / "rc_smoke.log").is_file()
