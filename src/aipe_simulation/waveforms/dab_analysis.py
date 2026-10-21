"""DAB-specific engineering summary derived from an executed waveform dataset.

The summary is the machine-readable interface consumed by downstream agents:

* ports: DC voltages, currents, powers, efficiency, loss, cycle energy;
* series path: inductor current RMS/peak, inductor voltage, magnetising current;
* bridges: AC bridge voltages and their primary-referred comparison;
* transformer: volt-second balance and flux-linkage swing;
* switches: per-device RMS/average/peak currents, conduction fraction and
  charge, turn-off currents (switching stress for E_off), turn-on currents,
  leg current at the ideal switching instant and the ZVS current condition,
  drain-source voltage stress;
* energy balance: accounted resistive losses versus the port power difference;
* steady-state identification, symmetry/periodicity diagnostics and the
  solver time-step statistics.

``valid`` is ``False`` whenever the run did not reach periodic steady state;
all numbers are then diagnostic only and must not feed design decisions.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..dab.gating import HIGH_SIDE, LEG_OF, PRIMARY, SWITCHES, SpsTiming
from ..dab.spec import DabCircuitSpec
from .dataset import WaveformDataset
from .metrics import (average, average_power, half_wave_symmetry_error, integrate, interp_at, peak,
                      periodicity_error, rms, threshold_crossings, volt_seconds)
from .steady_state import find_steady_state_window

LEG_CURRENT_SIGN = {"A": ("i_L", +1.0), "B": ("i_L", -1.0), "C": ("i_s", -1.0), "D": ("i_s", +1.0)}


def _q(value: float, unit: str) -> dict:
    return {"value": float(value), "unit": unit}


def _switch_summary(w: WaveformDataset, s: str, spec: DabCircuitSpec, timing: SpsTiming, t0: float, t1: float,
                    n_cycles: int, i_min_zvs: float) -> dict:
    t = w.time
    i = w.get(f"i_{s}")
    gate = w.get(f"g_{s}")
    v_ds = w.get(f"v_ds_{s}")
    vg_half = spec.switch.gate_voltage / 2
    on_edges = threshold_crossings(t, gate, vg_half, "rising")
    off_edges = threshold_crossings(t, gate, vg_half, "falling")
    # Keep only edges with data margin on both sides.
    margin = 2 * spec.t_max
    on_edges = on_edges[(on_edges > t0 + margin) & (on_edges < t1 - margin)]
    off_edges = off_edges[(off_edges > t0 + margin) & (off_edges < t1 - margin)]
    i_off = interp_at(t, i, off_edges, side="before") if off_edges.size else np.array([])
    i_on = interp_at(t, i, on_edges, side="after") if on_edges.size else np.array([])
    v_ds_before_on = interp_at(t, v_ds, on_edges, side="before") if on_edges.size else np.array([])
    v_ds_after_off = interp_at(t, v_ds, off_edges + spec.t_max * 4, side="exact") if off_edges.size else np.array([])
    # Leg current at the ideal switching instant preceding each turn-on (centre of dead band).
    leg_signal, sign = LEG_CURRENT_SIGN[LEG_OF[s]]
    leg = sign * w.get(leg_signal)
    ideal_instants = on_edges - spec.dead_time / 2
    i_leg = interp_at(t, leg, ideal_instants, side="exact") if on_edges.size else np.array([])
    high = s in HIGH_SIDE
    zvs_ok = (i_leg < -i_min_zvs) if high else (i_leg > i_min_zvs)
    pk = peak(t, i)
    thr = 0.01 * max(pk["abs_max"], 1e-9)
    conducting = np.abs(i) > thr
    conduction_fraction = float(integrate(t, conducting.astype(float)) / (t1 - t0))
    q_fwd = integrate(t, np.clip(i, 0, None)) / n_cycles
    q_rev = integrate(t, np.clip(i, None, 0)) / n_cycles
    return {
        "id": s, "leg": LEG_OF[s], "side": "high" if high else "low",
        "bridge": "primary" if s in PRIMARY else "secondary",
        "current_rms": _q(rms(t, i), "A"), "current_avg": _q(average(t, i), "A"),
        "current_peak_forward": _q(pk["max"], "A"), "current_peak_reverse": _q(pk["min"], "A"),
        "forward_charge_per_cycle": _q(q_fwd, "C"), "reverse_charge_per_cycle": _q(q_rev, "C"),
        "conduction_fraction": _q(conduction_fraction, "1"),
        "turn_off_events": int(off_edges.size), "turn_on_events": int(on_edges.size),
        "turn_off_current": {"values_A": [float(v) for v in i_off], "mean_abs_A": float(np.mean(np.abs(i_off))) if i_off.size else None,
                             "max_abs_A": float(np.max(np.abs(i_off))) if i_off.size else None},
        "turn_on_current": {"values_A": [float(v) for v in i_on], "max_abs_A": float(np.max(np.abs(i_on))) if i_on.size else None},
        "leg_current_at_switching_instant": {"values_A": [float(v) for v in i_leg],
                                             "sign_convention": f"{sign:+.0f} * {leg_signal}; current leaving the leg mid-node into the AC circuit"},
        "zvs_current_condition": {"rule": ("high side needs leg current < -i_min" if high else "low side needs leg current > i_min"),
                                  "i_min_A": i_min_zvs, "per_event": [bool(v) for v in zvs_ok],
                                  "all_events_met": bool(zvs_ok.all()) if zvs_ok.size else None,
                                  "fraction_met": float(zvs_ok.mean()) if zvs_ok.size else None},
        "v_ds_max": _q(float(np.max(v_ds)), "V"), "v_ds_min": _q(float(np.min(v_ds)), "V"),
        "v_ds_before_turn_on": {"values_V": [float(v) for v in v_ds_before_on]},
        "v_ds_after_turn_off": {"values_V": [float(v) for v in v_ds_after_off]},
    }


def analyse_dab_dataset(ds: WaveformDataset, spec: DabCircuitSpec, timing: Optional[SpsTiming] = None,
                        rel_tol: float = 1e-3, window_cycles: int = 4, periodicity_tol: float = 1e-2,
                        i_min_zvs: float = 0.0) -> dict:
    timing = timing or SpsTiming(spec.f_sw, spec.phi_rad, spec.dead_time, spec.switch.gate_voltage, spec.switch.gate_rise_fall)
    T = spec.period
    t = ds.time
    ss = find_steady_state_window(t, ds.get("i_L"), T, 0.0, rel_tol, window_cycles, periodicity_tol)
    summary: dict = {
        "schema": "aipe-dab-waveform-summary/0.1",
        "spec_sha256": spec.sha256(), "dataset_sha256": ds.sha256(),
        "steady_state": ss.to_dict(), "valid": bool(ss.ok),
        "status": "steady_state" if ss.ok else "not_steady_state",
        "conventions": {
            "time_origin": "centre of primary positive half-cycle (S1, S4 on)",
            "i_L": "series inductor current from node a towards the transformer",
            "i_s": "secondary current out of the transformer into node c",
            "i_dc1": "-i(V1): current delivered by port 1 into the converter",
            "i_dc2": "i(V2): current delivered by the converter into port 2",
            "p_1": "v_dc1 * i_dc1 (positive = power entering from port 1)",
            "p_2": "v_dc2 * i_dc2 (positive = power leaving into port 2)",
            "switch_current": "positive = drain-to-source conduction",
        },
        "numerical": {"timestep": ds.timestep_statistics(), "solver_options": spec.sim.__dict__,
                      "t_max_requested": spec.t_max},
    }
    if ss.t0 is None:
        # Not even a window could be formed; fall back to the last available cycles for diagnostics.
        k_end = int(np.floor(t[-1] / T))
        t1 = k_end * T
        t0 = max(t1 - window_cycles * T, float(t[0]))
        if t1 - t0 < T:
            summary["diagnostic_note"] = "fewer than one complete cycle available; no metrics computed"
            return summary
    else:
        t0, t1 = ss.t0, ss.t1
    n_cycles = max(int(round((t1 - t0) / T)), 1)
    w = ds.window(t0, t1)
    tw = w.time
    summary["window"] = {"t0": t0, "t1": t1, "cycles": n_cycles, "samples": w.n_points}

    v1, i1, v2, i2 = w.get("v_dc1"), w.get("i_dc1"), w.get("v_dc2"), w.get("i_dc2")
    p1, p2 = average_power(tw, v1, i1), average_power(tw, v2, i2)
    direction = "port1_to_port2" if p1 >= 0 else "port2_to_port1"
    eff = (p2 / p1) if (p1 > 0 and p2 > 0) else ((p1 / p2) if (p1 < 0 and p2 < 0) else None)
    summary["ports"] = {
        "power_flow_direction": direction,
        "port1": {"voltage_avg": _q(average(tw, v1), "V"), "current_avg": _q(average(tw, i1), "A"),
                  "current_rms": _q(rms(tw, i1), "A"), "power_avg": _q(p1, "W"), "energy_per_cycle": _q(p1 * T, "J"),
                  "voltage_ripple_pp": _q(peak(tw, v1)["max"] - peak(tw, v1)["min"], "V")},
        "port2": {"voltage_avg": _q(average(tw, v2), "V"), "current_avg": _q(average(tw, i2), "A"),
                  "current_rms": _q(rms(tw, i2), "A"), "power_avg": _q(p2, "W"), "energy_per_cycle": _q(p2 * T, "J"),
                  "voltage_ripple_pp": _q(peak(tw, v2)["max"] - peak(tw, v2)["min"], "V")},
        "loss_total": _q(p1 - p2, "W"),
        "efficiency": _q(eff, "1") if eff is not None else None,
    }
    i_L, v_L, i_m, i_s, i_p = w.get("i_L"), w.get("v_L"), w.get("i_m"), w.get("i_s"), w.get("i_p_ideal")
    pk_L, pk_s, pk_m = peak(tw, i_L), peak(tw, i_s), peak(tw, i_m)
    summary["series_path"] = {
        "i_L_rms": _q(rms(tw, i_L), "A"), "i_L_peak_abs": _q(pk_L["abs_max"], "A"), "i_L_max": _q(pk_L["max"], "A"),
        "i_L_min": _q(pk_L["min"], "A"), "i_L_avg": _q(average(tw, i_L), "A"),
        "v_L_rms": _q(rms(tw, v_L), "V"), "v_L_peak_abs": _q(peak(tw, v_L)["abs_max"], "V"),
        "i_p_ideal_rms": _q(rms(tw, i_p), "A"), "i_p_ideal_peak_abs": _q(peak(tw, i_p)["abs_max"], "A"),
        "i_s_rms": _q(rms(tw, i_s), "A"), "i_s_peak_abs": _q(pk_s["abs_max"], "A"), "i_s_avg": _q(average(tw, i_s), "A"),
        "i_m_rms": _q(rms(tw, i_m), "A"), "i_m_peak_abs": _q(pk_m["abs_max"], "A"), "i_m_avg": _q(average(tw, i_m), "A"),
        "l_total_primary": _q(spec.l_total_primary, "H"), "l_ext": _q(spec.l_ext, "H"),
        "l_leakage_primary_referred": _q(spec.l_lk_p + spec.l_lk_s * spec.n_ratio ** 2, "H"),
    }
    v_ab, v_cd, v_cd_ref, v_tp = w.get("v_ab"), w.get("v_cd"), w.get("v_cd_ref"), w.get("v_tp")
    summary["bridges"] = {
        "v_ab": {"rms": _q(rms(tw, v_ab), "V"), "max": _q(peak(tw, v_ab)["max"], "V"), "min": _q(peak(tw, v_ab)["min"], "V"), "avg": _q(average(tw, v_ab), "V")},
        "v_cd": {"rms": _q(rms(tw, v_cd), "V"), "max": _q(peak(tw, v_cd)["max"], "V"), "min": _q(peak(tw, v_cd)["min"], "V"), "avg": _q(average(tw, v_cd), "V")},
        "v_cd_primary_referred": {"rms": _q(rms(tw, v_cd_ref), "V"), "max": _q(peak(tw, v_cd_ref)["max"], "V")},
        "measured_phase_shift": _measured_phase_shift(tw, v_ab, v_cd, T),
        "ideal_switching_instants_in_window": {
            "primary": timing.ideal_switching_instants("primary", t1, t0),
            "secondary": timing.ideal_switching_instants("secondary", t1, t0)},
    }
    vs = volt_seconds(tw, v_tp, t0, T)
    summary["transformer"] = {
        "turns_ratio_np_ns": _q(spec.n_ratio, "1"), "magnetising_inductance_primary": _q(spec.l_m, "H"),
        "primary_voltage_rms": _q(rms(tw, v_tp), "V"),
        "net_volt_seconds_per_cycle": _q(vs["net_volt_seconds"], "s*V"),
        "flux_linkage_peak_to_peak": _q(vs["flux_linkage_peak_to_peak"], "s*V"),
        "volt_second_relative_imbalance": _q(vs["relative_imbalance"], "1"),
        "note": "flux density requires N_p and A_e from the magnetics design: B_pp = flux_linkage_pp / (N_p * A_e)",
    }
    summary["symmetry"] = {
        "i_L_half_wave_antisymmetry_error": _q(half_wave_symmetry_error(tw, i_L, T), "1"),
        "i_L_periodicity_error": _q(periodicity_error(tw, i_L, T), "1"),
        "v_ab_periodicity_error": _q(periodicity_error(tw, v_ab, T), "1"),
        "i_s_half_wave_antisymmetry_error": _q(half_wave_symmetry_error(tw, i_s, T), "1"),
    }
    switches = [_switch_summary(w, s, spec, timing, t0, t1, n_cycles, i_min_zvs) for s in SWITCHES]
    summary["switches"] = switches
    p_r_p = rms(tw, i_L) ** 2 * spec.r_series_p
    p_r_s = rms(tw, i_s) ** 2 * spec.r_series_s
    p_ron = sum(sw["current_rms"]["value"] ** 2 for sw in switches) * spec.switch.r_on
    # True switch-pair dissipation from the waveforms: average of v_ds * i over the window (channel + diode + Coss branch).
    p_switches_true = sum(average_power(tw, w.get(f"v_ds_{s}"), w.get(f"i_{s}")) for s in SWITCHES)
    # Stored-energy change of the DC capacitors over the window (positive = capacitors still absorbing power).
    # Capacitor drift from cycle-averaged voltages of the first and last cycle in the window (ripple-free).
    def _cycle_mean(signal: np.ndarray, a: float, b: float) -> float:
        mask = (tw >= a - 1e-15) & (tw <= b + 1e-15)
        return float(average(tw[mask], signal[mask])) if np.count_nonzero(mask) >= 2 else float("nan")

    p_cap = {}
    span = (n_cycles - 1) * T if n_cycles > 1 else T
    for label, cap, signal in (("port2_capacitor", spec.port2.capacitance if spec.port2.type == "rc_load" else 0.0, v2),
                               ("dc_link1_capacitor", spec.dc_link1.capacitance, v1)):
        if cap > 0:
            v_first = _cycle_mean(signal, t0, t0 + T)
            v_last = _cycle_mean(signal, t1 - T, t1)
            p_cap[label] = 0.5 * cap * (v_last ** 2 - v_first ** 2) / span if n_cycles > 1 else 0.0
            # Total local + bulk capacitance shares the same voltage; include the decoupling branch energy.
    if spec.port2.type == "rc_load" and spec.port2.capacitance > 0 and spec.port2.local_decoupling_capacitance > 0:
        p_cap["port2_capacitor"] *= 1 + spec.port2.local_decoupling_capacitance / spec.port2.capacitance
    if spec.dc_link1.capacitance > 0 and spec.dc_link1.local_decoupling_capacitance > 0:
        p_cap["dc_link1_capacitor"] *= 1 + spec.dc_link1.local_decoupling_capacitance / spec.dc_link1.capacitance
    p_cap_total = sum(p_cap.values())
    unaccounted = p1 - p2 - p_cap_total - p_r_p - p_r_s - p_switches_true
    summary["energy_balance"] = {
        "p_in": _q(p1, "W"), "p_out": _q(p2, "W"),
        "p_capacitor_energy_change": {k: _q(v, "W") for k, v in p_cap.items()},
        "p_loss_total": _q(p1 - p2 - p_cap_total, "W"),
        "p_series_resistance_primary": _q(p_r_p, "W"), "p_series_resistance_secondary": _q(p_r_s, "W"),
        "p_switches_from_waveforms": _q(p_switches_true, "W"),
        "p_switch_on_resistance_estimate": _q(p_ron, "W"),
        "p_unaccounted": _q(unaccounted, "W"),
        "relative_unaccounted": _q(unaccounted / abs(p1) if p1 else 0.0, "1"),
        "note": ("p_switches_from_waveforms is the measured average of v_ds*i per switch pair (channel, diode and Coss branch); "
                 "p_switch_on_resistance_estimate is i_rms^2*Ron for comparison; remaining unaccounted power is ESR/damping/source resistance"),
    }
    # A port whose capacitor is still exchanging more than 1 % of the output power has not reached steady state.
    if p2 and abs(p_cap_total) > 0.01 * abs(p2):
        summary["valid"] = False
        summary["status"] = "not_steady_state"
        summary["steady_state"]["ok"] = False
        summary["steady_state"]["reason"] = (f"DC capacitor stored energy still changing: {p_cap_total:.2f} W over the window "
                                            f"(> 1 % of output power); extend the run")
    summary["ports"]["loss_total"] = _q(p1 - p2 - p_cap_total, "W")
    # Efficiency with the capacitor stored-energy drift attributed to the respective port.
    p_in_eff = p1 - p_cap.get("dc_link1_capacitor", 0.0)
    p_out_eff = p2 + p_cap.get("port2_capacitor", 0.0)
    if p_in_eff > 0 and p_out_eff > 0:
        summary["ports"]["efficiency_drift_corrected"] = _q(p_out_eff / p_in_eff, "1")
    elif p_in_eff < 0 and p_out_eff < 0:
        summary["ports"]["efficiency_drift_corrected"] = _q(p_in_eff / p_out_eff, "1")
    summary["energy_balance"]["p_in_effective"] = _q(p_in_eff, "W")
    summary["energy_balance"]["p_out_effective"] = _q(p_out_eff, "W")
    summary["zvs_overview"] = {
        s["id"]: s["zvs_current_condition"]["all_events_met"] for s in switches
    }
    return summary


def _measured_phase_shift(t: np.ndarray, v_ab: np.ndarray, v_cd: np.ndarray, T: float) -> dict:
    """Phase shift measured from the rising zero crossings of the two bridge voltages."""
    r_ab = threshold_crossings(t, v_ab, 0.0, "rising")
    r_cd = threshold_crossings(t, v_cd, 0.0, "rising")
    if r_ab.size == 0 or r_cd.size == 0:
        return {"available": False}
    deltas = []
    for ta in r_ab:
        later = r_cd[r_cd >= ta - T / 2]
        if later.size:
            d = (later[0] - ta)
            d = ((d + T / 2) % T) - T / 2  # wrap to [-T/2, T/2)
            deltas.append(d)
    if not deltas:
        return {"available": False}
    mean = float(np.mean(deltas))
    return {"available": True, "t_phi_mean": _q(mean, "s"), "phi_deg_mean": _q(mean / T * 360.0, "deg"),
            "t_phi_spread": _q(float(np.max(deltas) - np.min(deltas)), "s"), "events": len(deltas)}


def compare_with_reference(summary: dict, reference: dict, tolerance: float = 0.02) -> dict:
    """Compare selected summary quantities with reference values.

    ``reference`` maps a dotted path inside ``summary`` (e.g.
    ``"ports.port2.power_avg.value"``) to the expected number. Returns the
    relative error per item and an overall pass flag.
    """
    results = {}
    all_ok = True
    for path, expected in reference.items():
        node = summary
        try:
            for part in path.split("."):
                node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, IndexError, TypeError, ValueError):
            results[path] = {"expected": expected, "actual": None, "relative_error": None, "pass": False, "note": "missing"}
            all_ok = False
            continue
        actual = float(node)
        scale = abs(expected) if expected else 1.0
        err = abs(actual - expected) / scale
        ok = err <= tolerance
        all_ok &= ok
        results[path] = {"expected": expected, "actual": actual, "relative_error": err, "pass": ok}
    return {"tolerance": tolerance, "pass": all_ok, "items": results}
