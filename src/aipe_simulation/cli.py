"""Command-line interface: ``aipe-sim``.

    aipe-sim doctor                       locate and numerically qualify ngspice
    aipe-sim dab default-spec             print the default Level 1 specification (YAML)
    aipe-sim dab netlist --spec FILE      print the generated ngspice netlist
    aipe-sim dab run --spec FILE --out D  execute the experiment and write the run directory
    aipe-sim dab analyse --run D          recompute summary.json from a stored run
    aipe-sim control design               design the SPS voltage/current loops and print coefficients and margins
    aipe-sim control simulate --out D     closed-loop host simulation (JSON, HDF5 traces, figures)
    aipe-sim control verify --out D       compare the cycle-averaged plant with ngspice Level 1 runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .control.simulate import SCENARIOS, ControlDesign, design_controllers, run_baseline
from .control.verify import compare_power_with_ngspice, format_comparison_table
from .dab.netlist import build_dab_netlist
from .dab.run import reanalyse, run_dab
from .dab.spec import DabCircuitSpec
from .ngspice.locate import locate_ngspice, qualify_ngspice


def _load_spec(path: str) -> DabCircuitSpec:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) if path.lower().endswith((".yaml", ".yml")) else json.loads(text)
    return DabCircuitSpec.from_dict(data)


def _load_design(path: str | None) -> ControlDesign:
    if not path:
        return ControlDesign()
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) if path.lower().endswith((".yaml", ".yml")) else json.loads(text)
    return ControlDesign.from_dict(data)


def cmd_doctor(args: argparse.Namespace) -> int:
    info = locate_ngspice(args.ngspice)
    if info is None:
        print(json.dumps({"ngspice": None, "message": "ngspice not found; set AIPE_NGSPICE or install ngspice"}, indent=2))
        return 1
    qualify_ngspice(info, Path(args.workdir) if args.workdir else None)
    print(json.dumps({"ngspice": info.to_dict()}, indent=2, default=str))
    return 0 if info.qualified else 2


def cmd_default_spec(args: argparse.Namespace) -> int:
    print(yaml.safe_dump(DabCircuitSpec().to_dict(), sort_keys=False))
    return 0


def cmd_netlist(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec) if args.spec else DabCircuitSpec()
    text = build_dab_netlist(spec)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec) if args.spec else DabCircuitSpec()
    if args.cycles:
        spec.sim.cycles = args.cycles
    if args.max_step_fraction:
        spec.sim.max_step_fraction = args.max_step_fraction
    result = run_dab(spec, args.out, ngspice=args.ngspice)
    brief = {"run_dir": result.run_dir, "succeeded": result.succeeded, "valid": result.valid, "status": result.status,
             "messages": result.messages, "spec_sha256": result.spec_sha256}
    if result.summary:
        ports = result.summary.get("ports", {})
        brief["p_in_W"] = ports.get("port1", {}).get("power_avg", {}).get("value")
        brief["p_out_W"] = ports.get("port2", {}).get("power_avg", {}).get("value")
        brief["i_L_rms_A"] = result.summary.get("series_path", {}).get("i_L_rms", {}).get("value")
    print(json.dumps(brief, indent=2, default=str))
    return 0 if result.succeeded else 1


def cmd_analyse(args: argparse.Namespace) -> int:
    summary = reanalyse(args.run)
    print(json.dumps({"valid": summary.get("valid"), "status": summary.get("status"),
                      "steady_state": summary.get("steady_state", {}).get("reason")}, indent=2))
    return 0 if summary.get("valid") else 2


def cmd_control_design(args: argparse.Namespace) -> int:
    design = _load_design(args.design)
    controllers = design_controllers(design)
    print(json.dumps({"design_sha256": design.sha256(), "design": design.to_dict(), "controllers": controllers.report},
                     indent=2, default=str))
    return 0 if all(loop["closed_loop_stable"] for loop in controllers.report["loops"].values()) else 2


def cmd_control_simulate(args: argparse.Namespace) -> int:
    design = _load_design(args.design)
    scenarios = tuple(args.scenario) if args.scenario else tuple(SCENARIOS)
    summary = run_baseline(design, args.out, scenarios=scenarios, figures=not args.no_figure)
    brief = {"out_dir": args.out, "design_sha256": summary["design_sha256"], "summary": summary.get("summary_path"),
             "loops": {name: {k: loop[k] for k in ("gain_crossover_hz", "phase_margin_deg", "gain_margin_db", "closed_loop_stable")}
                       for name, loop in summary["controllers"]["loops"].items()},
             "scenarios": {name: {"final_mode": entry["final_mode"], "trips": [t["cause"] for t in entry["trips"]],
                                  "figure": entry.get("figure")} for name, entry in summary["scenarios"].items()}}
    print(json.dumps(brief, indent=2, default=str))
    return 0


def cmd_control_verify(args: argparse.Namespace) -> int:
    phi = tuple(args.phi) if args.phi else (10.0, 22.5, 35.0)
    report = compare_power_with_ngspice(phi, args.out, ngspice=args.ngspice, cycles=args.cycles)
    sys.stdout.write(format_comparison_table(report))
    print(json.dumps({"all_valid": report["all_valid"], "max_abs_rel_err_p2": report["max_abs_rel_err_p2"],
                      "report": report["report_path"]}, indent=2))
    return 0 if report["all_valid"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aipe-sim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="locate and qualify ngspice")
    doctor.add_argument("--ngspice", help="explicit path to ngspice_con/ngspice")
    doctor.add_argument("--workdir", help="directory for the qualification run")
    doctor.set_defaults(func=cmd_doctor)
    dab = sub.add_parser("dab", help="dual active bridge experiments")
    dab_sub = dab.add_subparsers(dest="dab_command", required=True)
    p = dab_sub.add_parser("default-spec", help="print the default specification")
    p.set_defaults(func=cmd_default_spec)
    p = dab_sub.add_parser("netlist", help="print or write the ngspice netlist")
    p.add_argument("--spec")
    p.add_argument("--out")
    p.set_defaults(func=cmd_netlist)
    p = dab_sub.add_parser("run", help="execute a DAB experiment")
    p.add_argument("--spec")
    p.add_argument("--out", required=True)
    p.add_argument("--ngspice")
    p.add_argument("--cycles", type=int)
    p.add_argument("--max-step-fraction", type=int)
    p.set_defaults(func=cmd_run)
    p = dab_sub.add_parser("analyse", help="recompute the summary of a stored run")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_analyse)
    control = sub.add_parser("control", help="digital SPS control baseline (host-side models)")
    control_sub = control.add_subparsers(dest="control_command", required=True)
    p = control_sub.add_parser("design", help="design both loops and print coefficients and z-plane margins")
    p.add_argument("--design", help="ControlDesign JSON/YAML file (defaults to the 10 kW baseline)")
    p.set_defaults(func=cmd_control_design)
    p = control_sub.add_parser("simulate", help="closed-loop host simulation of the canonical scenarios")
    p.add_argument("--design")
    p.add_argument("--out", required=True)
    p.add_argument("--scenario", action="append", choices=sorted(SCENARIOS), help="repeatable; default: all")
    p.add_argument("--no-figure", action="store_true")
    p.set_defaults(func=cmd_control_simulate)
    p = control_sub.add_parser("verify", help="compare the cycle-averaged plant with ngspice Level 1 runs")
    p.add_argument("--out", required=True)
    p.add_argument("--phi", type=float, action="append", help="phase shift in degrees; repeatable (default 10, 22.5, 35)")
    p.add_argument("--ngspice")
    p.add_argument("--cycles", type=int, default=12)
    p.set_defaults(func=cmd_control_verify)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
