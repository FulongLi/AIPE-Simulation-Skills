"""Run an ngspice netlist in batch mode and collect reproducible evidence.

Every run records the exact command, working directory, solver version,
netlist SHA-256, exit status, wall-clock duration, warnings and errors parsed
from the solver log, and whether a raw output file with transient data was
produced. A run is ``succeeded`` only when ngspice exited normally, did not
report an aborted analysis and wrote transient data.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Union

from .locate import NgspiceInfo, locate_ngspice
from .rawfile import RawPlot, read_raw, transient_plot

_ABORT_PATTERNS = (
    "simulation(s) aborted",
    "timestep too small",
    "singular matrix",
    "doanalyses: tran:",
    "fatal error",
    "no such file",
    "cannot open",
)


@dataclass
class NgspiceRun:
    netlist_path: str
    raw_path: str
    log_path: str
    command: list[str]
    workdir: str
    returncode: Optional[int]
    duration_s: float
    ngspice_path: str
    ngspice_version: str
    netlist_sha256: str
    platform: str
    succeeded: bool
    timed_out: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stdout_tail: str = ""
    n_points: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Union[str, Path]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_log(text: str) -> tuple[list[str], list[str]]:
    warnings, errors = [], []
    for line in text.splitlines():
        low = line.lower()
        if "warning" in low:
            warnings.append(line.strip())
        if "error" in low or any(p in low for p in _ABORT_PATTERNS):
            errors.append(line.strip())
    # ngspice prints many identical warnings for repeated events; keep unique.
    def unique(items: list[str]) -> list[str]:
        seen, out = set(), []
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out
    return unique(warnings)[:200], unique(errors)[:200]


def run_netlist(netlist_text: str, workdir: Union[str, Path], name: str = "circuit",
                ngspice: Optional[Union[str, NgspiceInfo]] = None, timeout_s: float = 1800.0,
                extra_args: Optional[list[str]] = None) -> tuple[NgspiceRun, Optional[RawPlot]]:
    """Write ``netlist_text`` to ``workdir/name.cir`` and run ngspice in batch mode.

    Returns the run record and the parsed transient plot (``None`` on failure).
    The netlist must contain ``.save`` statements (or none, saving everything)
    and an analysis statement; raw data is written with ``-r``.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    if isinstance(ngspice, NgspiceInfo):
        info = ngspice
    else:
        info = locate_ngspice(ngspice)
    if info is None:
        raise FileNotFoundError("ngspice executable not found; set AIPE_NGSPICE or install ngspice")
    netlist_path = workdir / f"{name}.cir"
    raw_path = workdir / f"{name}.raw"
    log_path = workdir / f"{name}.log"
    netlist_path.write_text(netlist_text, encoding="utf-8", newline="\n")
    for stale in (raw_path, log_path):
        if stale.exists():
            stale.unlink()
    command = [info.path, "-b", "-r", raw_path.name, "-o", log_path.name, *(extra_args or []), netlist_path.name]
    # Binary raw files are smaller and exact; the Windows build defaults to ASCII otherwise.
    env = {**os.environ, "SPICE_ASCIIRAWFILE": "0"}
    started = time.perf_counter()
    timed_out = False
    returncode: Optional[int]
    stdout = ""
    try:
        completed = subprocess.run(command, cwd=str(workdir), capture_output=True, text=True,
                                   timeout=timeout_s, check=False, errors="replace", env=env)
        returncode = completed.returncode
        stdout = (completed.stdout or "") + (completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = ((exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
    duration = time.perf_counter() - started
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    warnings, errors = _scan_log(log_text + "\n" + stdout)
    plot: Optional[RawPlot] = None
    n_points = 0
    if raw_path.is_file() and raw_path.stat().st_size > 0:
        try:
            plot = transient_plot(read_raw(raw_path))
            n_points = int(plot.data.shape[0]) if plot is not None else 0
        except (ValueError, OSError) as exc:
            errors.append(f"raw file unreadable: {exc}")
    aborted = any(any(p in e.lower() for p in _ABORT_PATTERNS) for e in errors)
    succeeded = (returncode == 0) and not timed_out and plot is not None and n_points > 1 and not aborted
    run = NgspiceRun(netlist_path=str(netlist_path), raw_path=str(raw_path), log_path=str(log_path),
                     command=command, workdir=str(workdir), returncode=returncode, duration_s=duration,
                     ngspice_path=info.path, ngspice_version=info.version, netlist_sha256=sha256_text(netlist_text),
                     platform=f"{platform.system()} {platform.release()} {platform.machine()}",
                     succeeded=succeeded, timed_out=timed_out, warnings=warnings, errors=errors,
                     stdout_tail=stdout[-2000:], n_points=n_points)
    return run, (plot if succeeded else None)
