"""Verification of the cycle-averaged plant against executed ngspice Level 1 runs.

For each requested phase shift the Level 1 (ideal switching) DAB model of
:mod:`aipe_simulation.dab` is run with stiff voltage-source ports, started from
the analytic lossless series current at the time origin so that periodic
steady state is reached within a few cycles, and the steady-state port powers
and currents are compared with the lossless SPS law used by
:mod:`aipe_simulation.control.plant`. The Level 1 netlist contains the series
resistance ``r_series_p`` (20 mOhm default) and the switch on-resistance, so
the ngspice port-2 power is expected to fall slightly below the lossless value;
the comparison quantifies the error of the control plant rather than hiding it.

Nothing here is fabricated: every ngspice number comes from a run directory
written by :func:`aipe_simulation.dab.run.run_dab` (netlist, log, raw file,
HDF5 dataset and summary with hashes).
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Optional, Sequence, Union

from .. import __version__ as PACKAGE_VERSION
from ..dab.run import run_dab
from ..dab.spec import DabCircuitSpec
from ..ngspice.locate import NgspiceInfo
from .plant import DabSpsPlantParameters, series_current_at, series_current_rms, sps_output_current, sps_power

SCHEMA = "aipe-dab-sps-plant-verification/0.1"


def _rel(actual: Optional[float], expected: float) -> Optional[float]:
    if actual is None or expected == 0:
        return None
    return (actual - expected) / abs(expected)


def compare_power_with_ngspice(phi_deg_values: Sequence[float] = (10.0, 22.5, 35.0), out_dir: Union[str, Path] = "dab-plant-verification",
                               ngspice: Optional[Union[str, NgspiceInfo]] = None, cycles: int = 12, max_step_fraction: int = 200,
                               params: Optional[DabSpsPlantParameters] = None, v2: float = 400.0) -> dict:
    """Run the Level 1 model at each phase shift and tabulate the deviation from the lossless plant law."""
    params = params or DabSpsPlantParameters()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    solver = None
    for phi_deg in phi_deg_values:
        phi = math.radians(phi_deg)
        spec = DabCircuitSpec(name=f"dab-level1-plant-verification-phi{phi_deg:g}", v1=params.v1, v2=v2, f_sw=params.f_sw,
                              phi_deg=phi_deg, n_ratio=params.n_ratio, l_ext=params.l_total)
        spec.sim.cycles = cycles
        spec.sim.max_step_fraction = max_step_fraction
        spec.sim.use_initial_conditions = True
        spec.sim.initial_series_current = series_current_at(params.v1, v2, params.n_ratio, params.f_sw, params.l_total, phi, 0.0, "centre")
        result = run_dab(spec, out / f"phi_{phi_deg:g}".replace(".", "p"), ngspice=ngspice)
        p_plant = sps_power(params.v1, v2, params.n_ratio, params.f_sw, params.l_total, phi)
        i2_plant = sps_output_current(params.v1, params.n_ratio, params.f_sw, params.l_total, phi)
        i_l_rms_plant = series_current_rms(params.v1, v2, params.n_ratio, params.f_sw, params.l_total, phi)
        row = {"phi_deg": phi_deg, "status": result.status, "succeeded": result.succeeded, "valid": result.valid,
               "p_plant_W": p_plant, "i2_plant_A": i2_plant, "i1_plant_A": p_plant / params.v1, "i_l_rms_plant_A": i_l_rms_plant,
               "p2_ngspice_W": None, "p1_ngspice_W": None, "i2_ngspice_A": None, "i_l_rms_ngspice_A": None, "phi_measured_deg": None,
               "rel_err_p2": None, "rel_err_p1": None, "rel_err_i2": None, "rel_err_i_l_rms": None,
               "run_dir": result.run_dir, "netlist_sha256": result.run.get("netlist_sha256"), "dataset_sha256": result.dataset_sha256,
               "messages": result.messages}
        if result.succeeded and result.valid:
            s = result.summary
            ports = s["ports"]
            row.update({
                "p2_ngspice_W": ports["port2"]["power_avg"]["value"], "p1_ngspice_W": ports["port1"]["power_avg"]["value"],
                "i2_ngspice_A": ports["port2"]["current_avg"]["value"], "i_l_rms_ngspice_A": s["series_path"]["i_L_rms"]["value"],
                "phi_measured_deg": s["bridges"]["measured_phase_shift"].get("phi_deg_mean", {}).get("value"),
                "steady_state_window_cycles": s["steady_state"]["cycles_in_window"],
            })
            row["rel_err_p2"] = _rel(row["p2_ngspice_W"], p_plant)
            row["rel_err_p1"] = _rel(row["p1_ngspice_W"], p_plant)
            row["rel_err_i2"] = _rel(row["i2_ngspice_A"], i2_plant)
            row["rel_err_i_l_rms"] = _rel(row["i_l_rms_ngspice_A"], i_l_rms_plant)
        solver = solver or {"version": result.run.get("ngspice_version"), "path": result.run.get("ngspice_path"), "platform": result.run.get("platform")}
        rows.append(row)
    valid_rows = [r for r in rows if r["valid"]]
    report = {
        "schema": SCHEMA, "created_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "producer": {"id": "aipe.simulation-skills.control", "version": PACKAGE_VERSION},
        "plant_parameters": {**params.to_dict(), "v2_V": v2}, "ngspice": solver,
        "level1_model_note": "ngspice Level 1: ideal switches with Ron = 1 mOhm, antiparallel diodes, r_series_p = 20 mOhm, L_m = 1 mH, "
                             "stiff voltage-source ports; the control plant is lossless",
        "sim_settings": {"cycles": cycles, "max_step_fraction": max_step_fraction, "initial_series_current": "analytic lossless i_L at the centre origin"},
        "rows": rows, "all_valid": bool(valid_rows) and len(valid_rows) == len(rows),
        "max_abs_rel_err_p2": max((abs(r["rel_err_p2"]) for r in valid_rows), default=None),
        "max_abs_rel_err_p1": max((abs(r["rel_err_p1"]) for r in valid_rows), default=None),
        "max_abs_rel_err_i_l_rms": max((abs(r["rel_err_i_l_rms"]) for r in valid_rows), default=None),
    }
    (out / "plant_verification.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (out / "plant_verification.md").write_text(format_comparison_table(report), encoding="utf-8", newline="\n")
    report["report_path"] = str(out / "plant_verification.json")
    return report


def format_comparison_table(report: dict) -> str:
    """Markdown table of the plant-versus-ngspice comparison."""
    lines = ["| phi (deg) | P plant (W) | P2 ngspice (W) | err P2 (%) | P1 ngspice (W) | err P1 (%) | i_L RMS plant (A) | i_L RMS ngspice (A) | err (%) | phi measured (deg) | status |",
             "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]

    def pct(value: Optional[float]) -> str:
        return "n/a" if value is None else f"{value * 100:+.3f}"

    def num(value: Optional[float], fmt: str = "{:.1f}") -> str:
        return "n/a" if value is None else fmt.format(value)

    for r in report["rows"]:
        lines.append(f"| {r['phi_deg']:g} | {r['p_plant_W']:.1f} | {num(r['p2_ngspice_W'])} | {pct(r['rel_err_p2'])} | {num(r['p1_ngspice_W'])} | "
                     f"{pct(r['rel_err_p1'])} | {r['i_l_rms_plant_A']:.3f} | {num(r['i_l_rms_ngspice_A'], '{:.3f}')} | {pct(r['rel_err_i_l_rms'])} | "
                     f"{num(r['phi_measured_deg'], '{:.3f}')} | {r['status']} |")
    solver = report.get("ngspice") or {}
    lines.append("")
    lines.append(f"ngspice {solver.get('version', '?')} on {solver.get('platform', '?')}; cycles = {report['sim_settings']['cycles']}, "
                 f"t_max = T/{report['sim_settings']['max_step_fraction']}; {report['level1_model_note']}.")
    return "\n".join(lines) + "\n"
