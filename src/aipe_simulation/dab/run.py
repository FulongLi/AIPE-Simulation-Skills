"""End-to-end DAB experiment: specification -> netlist -> ngspice -> dataset -> summary.

Run directory contents::

    spec.json          the DabCircuitSpec actually used
    metadata.json      timing, switch table, saved vectors, derived quantities
    circuit.cir        netlist handed to ngspice (hash recorded in run.json)
    circuit.log        solver log
    circuit.raw        solver raw output (binary)
    waveforms.h5       WaveformDataset (HDF5) with units and provenance
    summary.json       engineering summary (see waveforms.dab_analysis)
    run.json           execution record: command, versions, status, hashes, timing
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Union

import numpy as np

from ..ngspice.locate import NgspiceInfo
from ..ngspice.runner import run_netlist, sha256_file
from ..waveforms.dab_analysis import analyse_dab_dataset
from ..waveforms.dataset import WaveformDataset
from .gating import SWITCHES, SpsTiming
from .netlist import _SWITCH_NODES, build_dab_netlist, netlist_metadata
from .spec import DabCircuitSpec

from .. import __version__ as PACKAGE_VERSION


@dataclass
class DabRunResult:
    run_dir: str
    spec_sha256: str
    succeeded: bool
    valid: bool
    status: str
    run: dict
    netlist_path: str
    dataset_path: Optional[str] = None
    dataset_sha256: Optional[str] = None
    summary_path: Optional[str] = None
    summary: dict = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_dataset(plot, spec: DabCircuitSpec, run_record: dict, metadata: dict) -> WaveformDataset:
    """Convert the ngspice transient plot into a WaveformDataset with derived channels."""
    t = np.asarray(plot.time, dtype=np.float64)
    ds = WaveformDataset(t, {}, {
        "format_note": "AIPE DAB waveform dataset; see conventions",
        "spec": spec.to_dict(), "spec_sha256": spec.sha256(),
        "timing": metadata["timing"], "switches": metadata["switches"],
        "solver": {"id": "ngspice", "version": run_record["ngspice_version"], "path": run_record["ngspice_path"],
                   "platform": run_record["platform"], "command": run_record["command"]},
        "netlist_sha256": run_record["netlist_sha256"], "created_at": _now(),
        "producer": {"id": "aipe.simulation-skills.dab", "version": PACKAGE_VERSION},
        "conventions": {
            "time_origin": "centre of primary positive half-cycle (S1, S4 on)",
            "phi_sign": "phi > 0: secondary lags, power flows port 1 -> port 2",
            "i_L": "from node a towards the transformer", "i_s": "out of transformer secondary into node c",
            "i_dc1": "-i(V1), delivered by port 1", "i_dc2": "i(V2), delivered to port 2",
            "switch_current": "positive = drain-to-source conduction",
        },
    })
    g = plot.get
    n = spec.n_ratio
    v = {name: np.real(g(f"v({name})")) for name in ("a", "b", "c", "d", "p_pos", "s_pos", "tp", "ts", "x1")}
    ds.add("v_a", v["a"], "V", "primary leg A mid-node voltage")
    ds.add("v_b", v["b"], "V", "primary leg B mid-node voltage")
    ds.add("v_c", v["c"], "V", "secondary leg C mid-node voltage")
    ds.add("v_d", v["d"], "V", "secondary leg D mid-node voltage")
    ds.add("v_dc1", v["p_pos"], "V", "port 1 DC-link voltage")
    ds.add("v_dc2", v["s_pos"], "V", "port 2 DC voltage")
    ds.add("v_ab", v["a"] - v["b"], "V", "primary AC bridge voltage v(a)-v(b)")
    ds.add("v_cd", v["c"] - v["d"], "V", "secondary AC bridge voltage v(c)-v(d)")
    ds.add("v_cd_ref", n * (v["c"] - v["d"]), "V", "primary-referred secondary bridge voltage n*v_cd")
    ds.add("v_tp", v["tp"] - v["b"], "V", "transformer primary winding voltage v(tp)-v(b)")
    ds.add("v_ts", v["ts"] - v["d"], "V", "transformer secondary terminal voltage v(ts)-v(d)")
    ds.add("v_L", v["a"] - v["x1"], "V", "external series inductor voltage")
    i_L = np.real(g("i(Lext)"))
    i_m = np.real(g("i(Lm)"))
    i_s = np.real(g("i(Vis)"))
    i_v1 = np.real(g("i(V1)"))
    i_v2 = np.real(g("i(V2)"))
    ds.add("i_L", i_L, "A", "external series inductor current", "from node a towards transformer")
    ds.add("i_m", i_m, "A", "magnetising current (primary referred)")
    ds.add("i_s", i_s, "A", "transformer secondary current", "out of transformer into node c")
    ds.add("i_p_ideal", i_s / n, "A", "ideal-transformer primary current i_s/n (excludes magnetising current)")
    ds.add("i_dc1", -i_v1, "A", "port 1 DC current", "positive into the converter")
    ds.add("i_dc2", i_v2, "A", "port 2 DC current", "positive out of the converter into port 2")
    ds.add("p_1", v["p_pos"] * (-i_v1), "W", "instantaneous power entering from port 1")
    ds.add("p_2", v["s_pos"] * i_v2, "W", "instantaneous power leaving into port 2")
    for s in SWITCHES:
        drain, source = _SWITCH_NODES[s]
        v_drain = v[drain] if drain != "0" else np.zeros_like(t)
        v_source = v[source] if source != "0" else np.zeros_like(t)
        ds.add(f"i_{s}", np.real(g(f"i(Vs{s})")), "A", f"{s} switch-pair current", "positive = drain to source")
        ds.add(f"v_ds_{s}", v_drain - v_source, "V", f"{s} drain-source voltage")
        ds.add(f"g_{s}", np.real(g(f"v(g{s[1]})")), "V", f"{s} gate signal")
    return ds


def run_dab(spec: DabCircuitSpec, out_dir: Union[str, Path], ngspice: Optional[Union[str, NgspiceInfo]] = None,
            analyse: bool = True, rel_tol: float = 1e-3, window_cycles: int = 4,
            periodicity_tol: float = 1e-2) -> DabRunResult:
    problems = spec.validate()
    if problems:
        raise ValueError("invalid DAB specification: " + "; ".join(problems))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    netlist = build_dab_netlist(spec)
    metadata = netlist_metadata(spec)
    (out_dir / "spec.json").write_text(json.dumps(spec.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True, default=str), encoding="utf-8")
    started = _now()
    run, plot = run_netlist(netlist, out_dir, name="circuit", ngspice=ngspice, timeout_s=spec.sim.timeout_s)
    run_record = {**run.to_dict(), "started_at": started, "finished_at": _now(), "producer": {"id": "aipe.simulation-skills.dab", "version": PACKAGE_VERSION}}
    result = DabRunResult(run_dir=str(out_dir), spec_sha256=spec.sha256(), succeeded=run.succeeded, valid=False,
                          status="solver_failed" if not run.succeeded else "solver_completed", run=run_record,
                          netlist_path=run.netlist_path)
    if not run.succeeded or plot is None:
        result.messages.append("ngspice did not complete the transient analysis; see circuit.log")
        result.messages.extend(run.errors[:10])
        (out_dir / "run.json").write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str), encoding="utf-8")
        return result
    ds = build_dataset(plot, spec, run_record, metadata)
    dataset_path = out_dir / "waveforms.h5"
    ds.save_hdf5(dataset_path)
    result.dataset_path = str(dataset_path)
    result.dataset_sha256 = ds.sha256()
    run_record["raw_sha256"] = sha256_file(run.raw_path)
    run_record["dataset_sha256"] = result.dataset_sha256
    run_record["dataset_file_sha256"] = sha256_file(dataset_path)
    if analyse:
        timing = SpsTiming(spec.f_sw, spec.phi_rad, spec.dead_time, spec.switch.gate_voltage, spec.switch.gate_rise_fall)
        summary = analyse_dab_dataset(ds, spec, timing, rel_tol=rel_tol, window_cycles=window_cycles, periodicity_tol=periodicity_tol)
        summary["run"] = {"run_dir": str(out_dir), "netlist_sha256": run.netlist_sha256, "solver": run_record["ngspice_version"],
                          "dataset": str(dataset_path), "dataset_sha256": result.dataset_sha256,
                          "warnings": run.warnings[:20], "n_warnings": len(run.warnings)}
        summary_path = out_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
        result.summary = summary
        result.summary_path = str(summary_path)
        result.valid = bool(summary.get("valid", False))
        result.status = summary.get("status", result.status)
        if not result.valid:
            result.messages.append(summary["steady_state"]["reason"])
    (out_dir / "run.json").write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str), encoding="utf-8")
    return result


def reanalyse(run_dir: Union[str, Path], **kwargs) -> dict:
    """Recompute the summary from a stored run directory (no solver execution)."""
    run_dir = Path(run_dir)
    spec = DabCircuitSpec.from_dict(json.loads((run_dir / "spec.json").read_text(encoding="utf-8")))
    ds = WaveformDataset.load_hdf5(run_dir / "waveforms.h5")
    summary = analyse_dab_dataset(ds, spec, **kwargs)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return summary
