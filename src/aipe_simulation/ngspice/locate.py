"""Locate and qualify an ngspice executable without assuming it is on PATH.

Search order (first hit wins):

1. ``AIPE_NGSPICE`` environment variable (full path to the executable).
2. ``ngspice_con`` / ``ngspice`` on PATH (``ngspice_con.exe`` is the Windows
   console build; ``ngspice.exe`` on Windows is the GUI build and is not used
   for batch runs).
3. ``AIPE_TOOLS_DIR/Spice64/bin`` when ``AIPE_TOOLS_DIR`` is set.
4. Common Windows install locations: ``C:\\Spice64``, ``%ProgramFiles%\\Spice64``,
   ``%LOCALAPPDATA%\\Programs\\Spice64``.
5. ``tools/Spice64/bin`` relative to the current working directory and its
   parents (portable workspace layout).

Qualification runs a tiny RC transient and compares the solver output with the
closed-form solution. Finding the binary is not a working capability; the
numerical test is.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class NgspiceInfo:
    path: str
    version: str
    version_output: str
    source: str
    qualified: bool = False
    qualification: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


_WINDOWS_CANDIDATES = [
    r"C:\Spice64\bin\ngspice_con.exe",
    r"C:\Spice64\bin\ngspice.exe",
]


def _candidate_paths() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    env = os.environ.get("AIPE_NGSPICE")
    if env:
        candidates.append((env, "AIPE_NGSPICE"))
    for name in ("ngspice_con", "ngspice"):
        found = shutil.which(name)
        if found:
            candidates.append((found, "PATH"))
    tools_dir = os.environ.get("AIPE_TOOLS_DIR")
    if tools_dir:
        for exe in ("ngspice_con.exe", "ngspice_con", "ngspice"):
            candidates.append((str(Path(tools_dir) / "Spice64" / "bin" / exe), "AIPE_TOOLS_DIR"))
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                candidates.append((str(Path(base) / "Spice64" / "bin" / "ngspice_con.exe"), "program-files"))
                candidates.append((str(Path(base) / "Programs" / "Spice64" / "bin" / "ngspice_con.exe"), "program-files"))
        candidates.extend((p, "well-known") for p in _WINDOWS_CANDIDATES)
    here = Path.cwd().resolve()
    for parent in [here, *here.parents]:
        for exe in ("ngspice_con.exe", "ngspice_con", "ngspice"):
            candidates.append((str(parent / "tools" / "Spice64" / "bin" / exe), "workspace-tools"))
    return candidates


def _version(path: str) -> tuple[str, str]:
    try:
        completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"{type(exc).__name__}: {exc}"
    text = (completed.stdout or "") + (completed.stderr or "")
    match = re.search(r"ngspice-(\d+(?:\.\d+)*(?:[+\w.-]*)?)", text)
    return (match.group(1) if match else "unknown"), text.strip()


def locate_ngspice(explicit: Optional[str] = None) -> Optional[NgspiceInfo]:
    """Return the first working ngspice executable, or ``None``."""
    candidates = [(explicit, "explicit")] if explicit else []
    candidates += _candidate_paths()
    seen = set()
    for path, source in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if not Path(path).is_file():
            continue
        if os.name == "nt" and Path(path).name.lower() == "ngspice.exe":
            # GUI build: only acceptable if no console build exists next to it.
            console = Path(path).with_name("ngspice_con.exe")
            if console.is_file():
                path = str(console)
        version, output = _version(path)
        if version:
            return NgspiceInfo(path=path, version=version, version_output=output, source=source)
    return None


RC_SMOKE_NETLIST = """* AIPE ngspice qualification: RC step response, tau = R*C = 1 ms
V1 in 0 PULSE(0 1 0 1n 1n 10m 20m)
R1 in out 1k
C1 out 0 1u
.tran 10u 5m 0 10u
.meas tran v_1tau FIND v(out) AT=1m
.meas tran v_3tau FIND v(out) AT=3m
.end
"""


def qualify_ngspice(info: NgspiceInfo, workdir: Optional[Path] = None, tolerance: float = 2e-3) -> NgspiceInfo:
    """Execute a minimal RC transient and compare with 1 - exp(-t/tau).

    The tolerance is relative to the analytic value at one and three time
    constants. A solver that does not reproduce an RC step within 0.2 % is not
    considered a qualified engineering capability.
    """
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="aipe-ngspice-qualify-"))
    workdir.mkdir(parents=True, exist_ok=True)
    netlist = workdir / "rc_smoke.cir"
    netlist.write_text(RC_SMOKE_NETLIST, encoding="utf-8")
    log = workdir / "rc_smoke.log"
    command = [info.path, "-b", "-o", str(log.name), str(netlist.name)]
    result = {"command": command, "workdir": str(workdir)}
    try:
        completed = subprocess.run(command, cwd=str(workdir), capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        info.qualification = {**result, "error": f"{type(exc).__name__}: {exc}"}
        info.qualified = False
        return info
    text = (completed.stdout or "") + (completed.stderr or "")
    if log.is_file():
        text += "\n" + log.read_text(encoding="utf-8", errors="replace")
    measured = {}
    for key in ("v_1tau", "v_3tau"):
        match = re.search(rf"{key}\s*=\s*([-+0-9.eE]+)", text)
        if match:
            measured[key] = float(match.group(1))
    expected = {"v_1tau": 1 - math.exp(-1.0), "v_3tau": 1 - math.exp(-3.0)}
    errors = {k: abs(measured[k] - expected[k]) / expected[k] for k in measured}
    ok = completed.returncode == 0 and set(measured) == set(expected) and all(e <= tolerance for e in errors.values())
    info.qualification = {**result, "returncode": completed.returncode, "measured": measured, "expected": expected,
                          "relative_errors": errors, "tolerance": tolerance, "passed": ok, "log": str(log)}
    info.qualified = ok
    return info
