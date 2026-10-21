"""Unit tests for the ngspice raw-file parser on synthetic files (no solver needed).

The files are built byte-for-byte the way ngspice writes them: an ASCII header
followed by ``Binary:`` + little-endian float64 records, or ``Values:`` + one
index line per point and one value per line. Both LF and CRLF line endings are
exercised because the Windows console build writes CRLF headers.
"""

from __future__ import annotations

import numpy as np
import pytest

from aipe_simulation.ngspice.rawfile import RawPlot, read_raw, transient_plot

VARIABLES = (("time", "time"), ("v(a)", "voltage"), ("v1#branch", "current"))
TIME = np.array([0.0, 1e-6, 2.5e-6, 4e-6, 5e-6])
V_A = np.array([0.0, 0.5, 1.0, 0.5, -0.25])
I_V1 = np.array([1e-3, -2e-3, 3e-3, 0.0, 4e-3])
DATA = np.column_stack([TIME, V_A, I_V1])
TITLE = "* synthetic AIPE test circuit: level 1"
DATE = "Wed Oct 21 12:00:00  2026"


def _header(plotname: str, variables, n_points: int, flags: str = "real") -> list[str]:
    lines = [
        f"Title: {TITLE}",
        f"Date: {DATE}",
        "Command: ngspice-47, Build Aug 11 2026   13:55:25",
        f"Plotname: {plotname}",
        f"Flags: {flags}",
        f"No. Variables: {len(variables)}",
        f"No. Points: {n_points}",
        "Variables:",
    ]
    lines += [f"\t{k}\t{name}\t{kind}" for k, (name, kind) in enumerate(variables)]
    return lines


def binary_plot(data: np.ndarray, plotname: str = "Transient Analysis", variables=VARIABLES, eol: str = "\n") -> bytes:
    """Real-valued binary plot: header + n_points * n_vars little-endian float64."""
    text = eol.join(_header(plotname, variables, data.shape[0], "real") + ["Binary:"]) + eol
    return text.encode("ascii") + np.ascontiguousarray(data, dtype="<f8").tobytes()


def complex_binary_plot(data: np.ndarray, plotname: str, variables, eol: str = "\n") -> bytes:
    """Complex binary plot: each value is a (real, imaginary) pair of float64."""
    text = eol.join(_header(plotname, variables, data.shape[0], "complex") + ["Binary:"]) + eol
    pairs = np.empty(data.shape + (2,), dtype="<f8")
    pairs[..., 0], pairs[..., 1] = data.real, data.imag
    return text.encode("ascii") + pairs.tobytes()


def ascii_plot(data: np.ndarray, plotname: str = "Transient Analysis", variables=VARIABLES, eol: str = "\n") -> bytes:
    lines = _header(plotname, variables, data.shape[0], "real") + ["Values:"]
    for k, row in enumerate(data):
        lines.append(f" {k}\t{float(row[0])!r}")
        lines += [f"\t{float(value)!r}" for value in row[1:]]
    return (eol.join(lines) + eol).encode("ascii")


def _check_transient(plot: RawPlot) -> None:
    assert plot.plotname == "Transient Analysis"
    assert plot.flags == "real"
    assert plot.title == TITLE
    assert plot.date == DATE
    assert plot.command.startswith("ngspice-47")
    assert plot.names == ["time", "v(a)", "v1#branch"]
    assert plot.variables == list(VARIABLES)
    assert plot.data.shape == (5, 3)
    assert plot.data.dtype == np.float64
    np.testing.assert_array_equal(plot.data, DATA)
    np.testing.assert_array_equal(plot.time, TIME)


@pytest.fixture
def binary_file(tmp_path):
    path = tmp_path / "lf.raw"
    path.write_bytes(binary_plot(DATA, eol="\n"))
    return path


# ---------------------------------------------------------------------------
# (a) / (b) binary real, LF and CRLF
# ---------------------------------------------------------------------------
def test_binary_real_lf(binary_file):
    plots = read_raw(binary_file)
    assert len(plots) == 1
    _check_transient(plots[0])


def test_binary_real_crlf(tmp_path):
    path = tmp_path / "crlf.raw"
    content = binary_plot(DATA, eol="\r\n")
    assert b"Binary:\r\n" in content
    path.write_bytes(content)
    plots = read_raw(path)
    assert len(plots) == 1
    plot = plots[0]
    _check_transient(plot)
    # No carriage return may leak into any parsed header field or variable name.
    for text in (plot.title, plot.date, plot.plotname, plot.flags, plot.command, *plot.names, *(k for _, k in plot.variables)):
        assert "\r" not in text


def test_binary_lf_and_crlf_give_identical_plots(tmp_path):
    lf, crlf = tmp_path / "a.raw", tmp_path / "b.raw"
    lf.write_bytes(binary_plot(DATA, eol="\n"))
    crlf.write_bytes(binary_plot(DATA, eol="\r\n"))
    a, b = read_raw(lf)[0], read_raw(crlf)[0]
    assert a.variables == b.variables
    assert (a.title, a.date, a.plotname, a.flags) == (b.title, b.date, b.plotname, b.flags)
    np.testing.assert_array_equal(a.data, b.data)


# ---------------------------------------------------------------------------
# (c) ASCII Values with CRLF
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("eol", ["\r\n", "\n"], ids=["crlf", "lf"])
def test_ascii_values(tmp_path, eol):
    path = tmp_path / "ascii.raw"
    content = ascii_plot(DATA, eol=eol)
    assert ("Values:" + eol).encode() in content
    path.write_bytes(content)
    plots = read_raw(path)
    assert len(plots) == 1
    _check_transient(plots[0])  # repr() round-trips every float exactly


# ---------------------------------------------------------------------------
# (d) two plots: operating point followed by transient
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_transient_plot_is_selected_from_multi_plot_file(tmp_path, eol):
    op_variables = (("v(a)", "voltage"), ("v1#branch", "current"))
    op_data = np.array([[0.75, -1.5e-3]])
    path = tmp_path / "two_plots.raw"
    path.write_bytes(binary_plot(op_data, "Operating Point", op_variables, eol) + binary_plot(DATA, eol=eol))
    plots = read_raw(path)
    assert [p.plotname for p in plots] == ["Operating Point", "Transient Analysis"]
    assert plots[0].names == ["v(a)", "v1#branch"]
    assert plots[0].data.shape == (1, 2)
    np.testing.assert_array_equal(plots[0].data, op_data)
    tran = transient_plot(plots)
    assert tran is plots[1]
    _check_transient(tran)
    assert transient_plot([plots[0]]) is None
    assert transient_plot([]) is None


def test_transient_plot_returns_last_transient():
    def plot(name):
        return RawPlot("", "", name, "real", [("time", "time")], np.zeros((1, 1)))
    plots = [plot("Transient Analysis"), plot("Operating Point"), plot("Transient Analysis")]
    assert transient_plot(plots) is plots[2]


# ---------------------------------------------------------------------------
# (e) truncated binary file keeps only the complete points
# ---------------------------------------------------------------------------
def test_truncated_binary_file_keeps_complete_points_only(tmp_path):
    content = binary_plot(DATA)
    record = DATA.shape[1] * 8
    header_len = len(content) - DATA.shape[0] * record
    # Header declares 5 points; keep 3 complete records plus one stray value.
    truncated = content[: header_len + 3 * record + 8]
    path = tmp_path / "truncated.raw"
    path.write_bytes(truncated)
    plots = read_raw(path)
    assert len(plots) == 1
    plot = plots[0]
    assert plot.data.shape == (3, 3)
    np.testing.assert_array_equal(plot.data, DATA[:3])
    np.testing.assert_array_equal(plot.time, TIME[:3])
    assert plot.names == ["time", "v(a)", "v1#branch"]


def test_complex_binary_plot(tmp_path):
    variables = (("frequency", "frequency"), ("v(a)", "voltage"))
    freq = np.array([1e3, 1e4, 1e5]) + 0j
    v = np.array([1.0 - 0.5j, 0.25 + 0.125j, -1e-3 + 2e-3j])
    data = np.column_stack([freq, v])
    path = tmp_path / "ac.raw"
    path.write_bytes(complex_binary_plot(data, "AC Analysis", variables))
    plot = read_raw(path)[0]
    assert plot.plotname == "AC Analysis"
    assert "complex" in plot.flags
    assert np.iscomplexobj(plot.data)
    np.testing.assert_array_equal(plot.data, data)
    np.testing.assert_array_equal(plot.get("v(a)"), v)
    assert transient_plot([plot]) is None


# ---------------------------------------------------------------------------
# RawPlot.get name resolution
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["i(V1)", "I(v1)", "i(v1)", "v1#branch", "V1#BRANCH", " v1#branch "])
def test_get_accepts_both_branch_current_spellings(binary_file, name):
    plot = read_raw(binary_file)[0]
    assert plot.has(name)
    np.testing.assert_array_equal(plot.get(name), I_V1)


@pytest.mark.parametrize("name", ["v(a)", "V(A)", "V(a)", " v(a)"])
def test_get_accepts_voltage_vector_case_insensitively(binary_file, name):
    plot = read_raw(binary_file)[0]
    assert plot.has(name)
    np.testing.assert_array_equal(plot.get(name), V_A)


def test_get_time_case_insensitively(binary_file):
    plot = read_raw(binary_file)[0]
    np.testing.assert_array_equal(plot.get("TIME"), TIME)
    np.testing.assert_array_equal(plot.get("Time"), plot.time)


def test_get_accepts_bare_node_name_for_stored_voltage_vector(binary_file):
    plot = read_raw(binary_file)[0]
    np.testing.assert_array_equal(plot.get("a"), V_A)
    np.testing.assert_array_equal(plot.get("A"), V_A)


def test_get_voltage_when_file_stores_bare_node_name(tmp_path):
    """'.save all' style files store node voltages as bare node names."""
    variables = (("time", "time"), ("a", "voltage"), ("v1#branch", "current"))
    path = tmp_path / "bare.raw"
    path.write_bytes(binary_plot(DATA, variables=variables))
    plot = read_raw(path)[0]
    np.testing.assert_array_equal(plot.get("a"), V_A)
    np.testing.assert_array_equal(plot.get("v(a)"), V_A)
    np.testing.assert_array_equal(plot.get("V(A)"), V_A)


def test_get_branch_when_file_stores_i_spelling(tmp_path):
    """ngspice 47 writes '.save i(V1)' as 'i(v1)'; both spellings must still resolve."""
    variables = (("time", "time"), ("v(a)", "voltage"), ("i(v1)", "current"))
    path = tmp_path / "ispell.raw"
    path.write_bytes(binary_plot(DATA, variables=variables))
    plot = read_raw(path)[0]
    np.testing.assert_array_equal(plot.get("i(V1)"), I_V1)
    np.testing.assert_array_equal(plot.get("v1#branch"), I_V1)
    np.testing.assert_array_equal(plot.get("V1#branch"), I_V1)


@pytest.mark.parametrize("name", ["v(zz)", "i(V9)", "zz#branch", "nonsense", "", "v()"])
def test_get_unknown_name_raises_keyerror(binary_file, name):
    plot = read_raw(binary_file)[0]
    assert not plot.has(name)
    with pytest.raises(KeyError) as excinfo:
        plot.get(name)
    message = str(excinfo.value)
    assert "available" in message
    assert "v1#branch" in message


def test_file_without_plots_raises(tmp_path):
    path = tmp_path / "garbage.raw"
    path.write_bytes(b"Title: nothing here\nDate: today\nNo marker follows\n")
    with pytest.raises(ValueError, match="no ngspice plots"):
        read_raw(path)
    empty = tmp_path / "empty.raw"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="no ngspice plots"):
        read_raw(empty)
