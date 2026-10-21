"""Parse ngspice raw output files (binary or ASCII, one or more plots).

The raw format is documented in the ngspice manual ("rawfile format"). A file
consists of one or more plots; each plot has an ASCII header::

    Title: ...
    Date: ...
    Plotname: Transient Analysis
    Flags: real
    No. Variables: 5
    No. Points: 1234
    Variables:
    \t0\ttime\ttime
    \t1\tv(a)\tvoltage
    ...
    Binary:

followed by ``No. Points`` records of ``No. Variables`` little-endian float64
values (``complex`` plots hold pairs). ASCII plots use ``Values:`` with one
index line per point followed by one value per line.

Vector names follow ngspice conventions: branch currents of sources are named
``<source>#branch`` (e.g. ``.save i(V1)`` produces ``v1#branch``). ``RawPlot.get``
accepts either spelling, case-insensitively.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import numpy as np


@dataclass
class RawPlot:
    title: str
    date: str
    plotname: str
    flags: str
    variables: list[tuple[str, str]]  # (name, type)
    data: np.ndarray  # shape (n_points, n_variables), float64 or complex128
    command: str = ""
    options: dict = field(default_factory=dict)

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.variables]

    def _index(self, name: str) -> int:
        key = name.strip().lower()
        lower = [n.lower() for n in self.names]
        if key in lower:
            return lower.index(key)
        match = re.fullmatch(r"i\((\w+)\)", key)
        if match and f"{match.group(1)}#branch" in lower:
            return lower.index(f"{match.group(1)}#branch")
        match = re.fullmatch(r"(\w+)#branch", key)
        if match and f"i({match.group(1)})" in lower:
            return lower.index(f"i({match.group(1)})")
        if key.startswith("v(") and key.endswith(")") and key[2:-1] in lower:
            return lower.index(key[2:-1])
        if f"v({key})" in lower:
            return lower.index(f"v({key})")
        raise KeyError(f"vector {name!r} not in raw plot; available: {self.names}")

    def get(self, name: str) -> np.ndarray:
        return self.data[:, self._index(name)]

    def has(self, name: str) -> bool:
        try:
            self._index(name)
            return True
        except KeyError:
            return False

    @property
    def time(self) -> np.ndarray:
        return np.real(self.get("time"))


def _parse_header(text: str) -> dict:
    header: dict = {"variables": []}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("Variables:"):
            i += 1
            while i < len(lines) and lines[i].strip():
                parts = lines[i].strip().split("\t") if "\t" in lines[i] else lines[i].split()
                if len(parts) >= 3:
                    header["variables"].append((parts[1].strip(), parts[2].strip()))
                elif len(parts) == 2:
                    header["variables"].append((parts[1].strip(), "unknown"))
                i += 1
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            header[key.strip().lower()] = value.strip()
        i += 1
    return header


def read_raw(path: Union[str, Path]) -> list[RawPlot]:
    """Read every plot in an ngspice raw file."""
    buf = Path(path).read_bytes()
    plots: list[RawPlot] = []
    pos = 0
    marker_re = re.compile(rb"(Binary|Values):\r?\n")
    while pos < len(buf):
        found = marker_re.search(buf, pos)
        if not found:
            break
        marker = found.start()
        bin_marker = marker if found.group(1) == b"Binary" else -1
        marker_len = found.end() - found.start()
        header_text = buf[pos:marker].decode("latin-1")
        header = _parse_header(header_text)
        n_vars = int(header.get("no. variables", len(header["variables"])))
        n_points = int(header.get("no. points", 0))
        flags = header.get("flags", "real")
        is_complex = "complex" in flags.lower()
        variables = header["variables"][:n_vars]
        data_start = marker + marker_len
        if marker == bin_marker:
            width = 16 if is_complex else 8
            n_bytes = n_points * n_vars * width
            chunk = buf[data_start:data_start + n_bytes]
            if len(chunk) < n_bytes:
                # Truncated file (e.g. aborted run): keep the complete points only.
                n_points = len(chunk) // (n_vars * width)
                chunk = chunk[: n_points * n_vars * width]
            if is_complex:
                raw = np.frombuffer(chunk, dtype="<f8").reshape(n_points, n_vars, 2)
                data = raw[:, :, 0] + 1j * raw[:, :, 1]
            else:
                data = np.frombuffer(chunk, dtype="<f8").reshape(n_points, n_vars).copy()
            pos = data_start + n_points * n_vars * width
        else:
            text = buf[data_start:].decode("latin-1")
            tokens: list[float] = []
            consumed = 0
            lines = text.splitlines(keepends=True)
            count_points = 0
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    consumed += len(line)
                    if count_points >= n_points and len(tokens) >= n_points * n_vars:
                        break
                    continue
                if stripped.startswith(("Title:", "Plotname:")):
                    break
                parts = stripped.split()
                if len(parts) == 2 and parts[0].isdigit():
                    count_points += 1
                    parts = parts[1:]
                for token in parts:
                    if "," in token:
                        re_, im_ = token.split(",")
                        tokens.append(complex(float(re_), float(im_)))  # type: ignore[arg-type]
                    else:
                        tokens.append(float(token))
                consumed += len(line)
                if count_points >= n_points and len(tokens) >= n_points * n_vars:
                    break
            arr = np.array(tokens[: n_points * n_vars])
            data = arr.reshape(n_points, n_vars) if n_points and n_vars else arr.reshape(0, max(n_vars, 1))
            pos = data_start + consumed
        plots.append(RawPlot(title=header.get("title", ""), date=header.get("date", ""),
                             plotname=header.get("plotname", ""), flags=flags, variables=variables,
                             data=data, command=header.get("command", ""),
                             options={k: v for k, v in header.items() if k.startswith("option")}))
    if not plots:
        raise ValueError(f"no ngspice plots found in {path}")
    return plots


def transient_plot(plots: list[RawPlot]) -> Optional[RawPlot]:
    """Return the transient analysis plot (the last one if several)."""
    found = [p for p in plots if "transient" in p.plotname.lower()]
    return found[-1] if found else None
