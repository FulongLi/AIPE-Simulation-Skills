"""Engineering figures from executed waveform datasets (matplotlib, optional).

Design rules applied: one y-axis per panel (no dual axes), categorical hues
assigned in fixed order, a legend whenever a panel shows two or more series,
units on every axis, recessive grid, and the solver attribution plus the input
hash in the figure title so a figure can be traced to its run. Text uses
neutral ink; colour is carried by the marks only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np

from .dataset import WaveformDataset

# Validated categorical palette (light surface), fixed slot order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
REFERENCE = "#8a897f"


def _mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "text.color": TEXT, "axes.labelcolor": TEXT_SECONDARY, "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY, "axes.edgecolor": GRID, "grid.color": GRID, "axes.grid": True,
        "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
        "lines.linewidth": 1.6, "legend.frameon": False, "font.size": 9, "axes.titlesize": 10,
        "legend.fontsize": 8.5, "axes.titlelocation": "left", "axes.titlepad": 22,
    })
    return plt


def _legend(ax, ncol: int) -> None:
    """Legend above the plotting area so it never covers the traces."""
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=ncol, borderaxespad=0.0)


def _title(summary: dict, what: str) -> str:
    run = summary.get("run", {})
    return (f"{what} — ngspice {run.get('solver', '?')} — spec {summary.get('spec_sha256', '')[:12]} — "
            f"window {summary.get('window', {}).get('cycles', '?')} cycles")


def _window(ds: WaveformDataset, summary: dict, cycles: int, period: float) -> WaveformDataset:
    w = summary.get("window", {})
    t1 = w.get("t1", float(ds.time[-1]))
    t0 = max(w.get("t0", float(ds.time[0])), t1 - cycles * period)
    return ds.window(t0, t1)


def plot_dab_overview(ds: WaveformDataset, summary: dict, path: Union[str, Path], cycles: int = 2) -> str:
    plt = _mpl()
    spec = ds.metadata["spec"]
    T = 1.0 / spec["f_sw"]
    w = _window(ds, summary, cycles, T)
    t_us = (w.time - w.time[0]) * 1e6
    fig, axes = plt.subplots(4, 1, figsize=(9, 10), sharex=True)
    ax = axes[0]
    ax.plot(t_us, w.get("v_ab"), color=SERIES[0], label="v_ab primary bridge")
    ax.plot(t_us, w.get("v_cd_ref"), color=SERIES[1], label=f"n·v_cd secondary bridge (n = {spec['n_ratio']:g})")
    ax.set_ylabel("voltage (V)")
    ax.set_title("Bridge voltages")
    _legend(ax, 2)
    ax = axes[1]
    ax.plot(t_us, w.get("i_L"), color=SERIES[0], label="i_L external inductor")
    ax.plot(t_us, w.get("i_p_ideal"), color=SERIES[1], label="i_s / n transformer (ideal part)")
    ax.plot(t_us, w.get("i_m"), color=SERIES[2], label="i_m magnetising")
    ax.set_ylabel("current (A)")
    ax.set_title("Series-path currents, primary side")
    _legend(ax, 3)
    ax = axes[2]
    ax.plot(t_us, w.get("i_dc1"), color=SERIES[0], label="i_dc1 port 1")
    ax.plot(t_us, w.get("i_dc2"), color=SERIES[1], label="i_dc2 port 2")
    ax.set_ylabel("current (A)")
    ax.set_title("DC port currents")
    _legend(ax, 2)
    ax = axes[3]
    ax.plot(t_us, w.get("p_1") / 1e3, color=SERIES[0], label="p_1 into converter")
    ax.plot(t_us, w.get("p_2") / 1e3, color=SERIES[1], label="p_2 out of converter")
    ax.set_ylabel("power (kW)")
    ax.set_xlabel("time within window (µs)")
    ax.set_title("Instantaneous port power")
    _legend(ax, 2)
    fig.suptitle(_title(summary, "DAB Level %d waveforms" % spec["level"]), x=0.02, ha="left", fontsize=10, color=TEXT)
    fig.text(0.02, 0.005, f"{spec['v1']:g} V → {spec['v2']:g} V, f_sw = {spec['f_sw']/1e3:g} kHz, φ = {spec['phi_deg']:g}°, "
             f"L_ext = {spec['l_ext']*1e6:g} µH, L_m = {spec['l_m']*1e3:g} mH; dataset {summary.get('dataset_sha256', '')[:12]}",
             fontsize=8, color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def plot_switch_currents(ds: WaveformDataset, summary: dict, path: Union[str, Path], cycles: int = 2) -> str:
    plt = _mpl()
    spec = ds.metadata["spec"]
    T = 1.0 / spec["f_sw"]
    w = _window(ds, summary, cycles, T)
    t_us = (w.time - w.time[0]) * 1e6
    fig, axes = plt.subplots(3, 1, figsize=(9, 8.5), sharex=True)
    for ax, group, label in ((axes[0], ("S1", "S2", "S3", "S4"), "Primary bridge switch currents"),
                             (axes[1], ("S5", "S6", "S7", "S8"), "Secondary bridge switch currents")):
        for k, s in enumerate(group):
            ax.plot(t_us, w.get(f"i_{s}"), color=SERIES[k], label=f"i_{s} ({'high' if k % 2 == 0 else 'low'} side)")
        ax.axhline(0, color=REFERENCE, linewidth=0.8)
        ax.set_ylabel("current (A)")
        ax.set_title(label + " (positive = drain to source)")
        _legend(ax, 4)
    ax = axes[2]
    ax.plot(t_us, w.get("v_ds_S1"), color=SERIES[0], label="v_ds S1")
    ax.plot(t_us, w.get("v_ds_S5"), color=SERIES[1], label="v_ds S5")
    ax.plot(t_us, w.get("g_S1") * 10, color=SERIES[2], label="gate S1 (×10)")
    ax.plot(t_us, w.get("g_S5") * 10, color=SERIES[3], label="gate S5 (×10)")
    ax.set_ylabel("voltage (V)")
    ax.set_xlabel("time within window (µs)")
    ax.set_title("Drain-source voltages and gate signals of one switch per bridge")
    _legend(ax, 4)
    fig.suptitle(_title(summary, "DAB Level %d device waveforms" % spec["level"]), x=0.02, ha="left", fontsize=10, color=TEXT)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def plot_cycle_convergence(summary: dict, path: Union[str, Path], reference_rms: Optional[float] = None,
                           label: str = "i_L RMS per switching cycle") -> str:
    plt = _mpl()
    per_cycle = summary["steady_state"]["per_cycle_metric"]
    cycles = [c["cycle"] for c in per_cycle]
    values = [c["value"] for c in per_cycle]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(cycles, values, color=SERIES[0], marker="o", markersize=3, label="simulated (ngspice)")
    if reference_rms is not None:
        ax.axhline(reference_rms, color=REFERENCE, linestyle="--", linewidth=1.2, label="analytic lossless SPS")
    w = summary.get("window")
    if w:
        T = w["t1"] - w["t0"]
        ax.axvspan(cycles[-w["cycles"]], cycles[-1], color=SERIES[2], alpha=0.12, label="steady-state window")
    ax.set_xlabel("switching cycle index")
    ax.set_ylabel("RMS current (A)")
    ax.set_title(label)
    _legend(ax, 2)
    fig.suptitle(_title(summary, "Start-up settling"), x=0.02, ha="left", fontsize=10, color=TEXT)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def plot_convergence_study(rows: Sequence[dict], path: Union[str, Path], keys: Sequence[tuple[str, str]] = (
        ("P2_W", "output power"), ("iL_rms_A", "i_L RMS"), ("iL_pk_A", "i_L peak"), ("iS1_off_A", "S1 turn-off current"))) -> str:
    """Relative deviation of observables from the finest-step run versus maximum time step."""
    plt = _mpl()
    rows = sorted(rows, key=lambda r: r["tmax_ns"], reverse=True)
    ref = rows[-1]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for k, (key, label) in enumerate(keys):
        x = [r["tmax_ns"] for r in rows[:-1]]
        y = [max(abs(r[key] - ref[key]) / abs(ref[key]), 1e-12) for r in rows[:-1]]
        ax.plot(x, y, color=SERIES[k], marker="o", markersize=4, label=label)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("maximum solver time step (ns)")
    ax.set_ylabel(f"relative deviation from t_max = {ref['tmax_ns']:g} ns run")
    ax.set_title("Time-step convergence of steady-state observables")
    _legend(ax, 4)
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)
