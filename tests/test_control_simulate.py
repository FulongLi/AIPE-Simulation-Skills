"""Closed-loop host simulation: design report, canonical scenarios, protection, linear-model consistency, artefacts."""

from __future__ import annotations

import json
import math
from dataclasses import replace

import numpy as np
import pytest

from aipe_simulation.control.plant import DabSpsPlant, DabSpsPlantParameters, output_current_gain, phase_shift_for_output_current
from aipe_simulation.control.simulate import (MODES, ControlDesign, Event, ProtectionLimits, Scenario, design_controllers, run_baseline,
                                              run_scenario)
from aipe_simulation.control.sps_modulator import SpsModulator
from aipe_simulation.control.verify import format_comparison_table
from aipe_simulation.control.ztf import ZTransfer
from aipe_simulation.waveforms.dataset import WaveformDataset


@pytest.fixture(scope="module")
def design() -> ControlDesign:
    return ControlDesign()


@pytest.fixture(scope="module")
def controllers(design):
    return design_controllers(design)


@pytest.fixture(scope="module")
def nominal(design, controllers):
    return run_scenario(design, "nominal", controllers)


@pytest.fixture(scope="module")
def fault(design, controllers):
    return run_scenario(design, "fault", controllers)


@pytest.fixture(scope="module")
def input_sag(design, controllers):
    return run_scenario(design, "input_sag", controllers)


def test_design_report_meets_loop_targets(design, controllers):
    r = controllers.report
    op = r["operating_point"]
    assert op["phi_deg"] == pytest.approx(22.5, abs=1e-9) and op["i2_A"] == 25.0
    assert op["dI2_dphi_A_per_rad"] == pytest.approx(54.5674, rel=1e-4)
    loops = r["loops"]
    cur = loops["current_loop_nominal"]
    assert cur["gain_crossover_hz"] == pytest.approx(2000.0, rel=2e-3)
    assert 80.0 < cur["phase_margin_deg"] < 100.0 and 9.0 < cur["gain_margin_db"] < 11.0
    vol = loops["voltage_loop_full_load"]
    assert vol["gain_crossover_hz"] == pytest.approx(300.0, rel=2e-3)
    assert vol["phase_margin_deg"] == pytest.approx(60.0, abs=0.5) and vol["gain_margin_db"] > 20.0
    assert loops["voltage_loop_no_load"]["phase_margin_deg"] > 45.0
    assert loops["current_loop_max_gain"]["gain_margin_db"] > 6.0
    for name, loop in loops.items():
        assert loop["closed_loop_stable"] is True, name
        assert loop["n_gain_crossovers"] == 1, name
    c = r["voltage_loop"]["coefficients"]
    assert 1 + c["a1"] + c["a2"] == pytest.approx(0.0, abs=1e-12)
    assert r["current_loop"]["kp_rad_per_A"] == pytest.approx(0.25 / 54.5674, rel=1e-4)
    assert r["current_loop"]["ki_per_sample_rad_per_A"] > 0
    assert r["sampling"]["f_s_Hz"] == pytest.approx(100e3)
    json.dumps(r)
    pi = controllers.new_pi()
    assert pi.u_max == pytest.approx(math.radians(45.0)) and pi.kp == controllers.pi_kp
    assert controllers.new_df22().y_max == 30.0


def test_nominal_scenario_regulates_through_all_events(nominal, design):
    m = nominal.metrics
    assert nominal.final_mode == "OFF" and nominal.trips == [] and m["trips"] == []
    st = m["startup"]
    assert 0.004 < st["handover_time_s"] < 0.010
    assert st["overshoot_after_handover_V"] < 10.0
    assert st["settling_time_to_1pct_after_handover_s"] < 0.005
    assert st["soft_start_i2_max_A"] < design.i_ref_limit_A
    assert st["soft_start_v2_min_V"] > 320.0
    w = m["windows"]
    step = w["load step 25 % -> 100 %"]
    assert step["max_deviation_pct"] < 6.0 and step["recovery_time_to_1pct_s"] < 0.005 and abs(step["final_error_V"]) < 0.5
    assert w["set-point 400 V -> 380 V"]["v2_min_V"] > 370.0 and abs(w["set-point 400 V -> 380 V"]["final_error_V"]) < 0.5
    release = w["load release 100 % -> 0"]
    assert release["max_deviation_pct"] < 8.0 and abs(release["final_error_V"]) < 0.5
    rev = w["power reversal: 12.5 A injected (5 kW regenerative)"]
    assert rev["phi_applied_min_deg"] < -8.0 and rev["i2_min_A"] < -10.0 and abs(rev["final_error_V"]) < 0.5
    assert rev["p2_min_W"] < -4000.0
    fwd = w["forward full load"]
    assert fwd["max_deviation_pct"] < 10.0 and fwd["recovery_time_to_1pct_s"] < 0.006
    limit = w["overload 133 % (current limit)"]
    # i_ref is clamped exactly; i2 follows the quantised phase shift (150 ps = 0.005 A at the operating point)
    assert limit["i2_max_A"] <= design.i_ref_limit_A + 0.05 and limit["i_ref_max_A"] <= design.i_ref_limit_A + 1e-9
    r_overload = 0.75 * design.v_ref ** 2 / design.nominal_power_W
    assert limit["v2_min_V"] == pytest.approx(design.i_ref_limit_A * r_overload, abs=3.0)  # droop into the current limit
    assert limit["final_error_V"] < -30.0
    assert limit["phi_applied_max_deg"] == pytest.approx(math.degrees(phase_shift_for_output_current(800.0, 2.0, 1e5, 35e-6, 30.0)), abs=0.05)
    assert w["overload removed"]["recovery_time_to_1pct_s"] is not None
    assert w["shutdown"]["mode_at_end"] == "OFF" and w["shutdown"]["i2_min_A"] == 0.0
    assert 0.120 < m["gates_off_time_s"] < 0.135
    tr = nominal.traces
    after_off = tr["t"] >= m["gates_off_time_s"]
    assert np.all(tr["i2"][after_off] == 0.0) and np.all(tr["enabled"][after_off] == 0.0)
    assert tr["v2"][-1] < 100.0  # capacitor discharges through the load after shutdown
    assert m["i_ref_within_limit"] is True
    assert m["i2_abs_max_A"] <= design.i_ref_limit_A + 0.05
    assert m["phi_applied_abs_max_deg"] <= design.phi_max_deg
    assert m["i_l_peak_max_A"] < design.protection.i_l_peak_trip_A
    assert design.protection.v2_under_V < m["v2_min_in_run_V"] and m["v2_max_in_run_V"] < design.protection.v2_over_V
    # every applied phase shift lies on the realisable register grid
    mod = SpsModulator(design.modulator_config())
    for phi in np.unique(tr["phi_applied"])[:: max(1, np.unique(tr["phi_applied"]).size // 200)]:
        assert mod.quantise_phase(float(phi)).phi_rad == pytest.approx(float(phi), abs=1e-15)
    assert m["quantisation_steps_in_phi_applied"] > 100
    # IDLE is left within the first sample (start event at t = 0), so it never appears in the recorded trace
    modes = [MODES[int(k)] for k in np.unique(tr["mode"])]
    assert set(modes) == {"SOFT_START", "RUN", "SHUTDOWN", "OFF"}
    assert tr["mode"][0] == MODES.index("SOFT_START")


def test_fault_scenario_trips_under_voltage_latches_and_blocks_restart(fault, design):
    assert len(fault.trips) == 1
    trip = fault.trips[0]
    assert trip["cause"] == "under_voltage" and trip["mode_before"] == "RUN"
    assert 0.025 <= trip["t"] <= 0.0255  # within 0.5 ms of the short circuit
    assert trip["v2_V"] < design.protection.v2_under_V
    tr = fault.traces
    after = tr["t"] >= trip["t"]
    assert np.all(tr["enabled"][after] == 0.0) and np.all(tr["i2"][after] == 0.0) and np.all(tr["phi_applied"][after] == 0.0)
    latched = tr["fault"] == 1.0
    assert tr["t"][latched].min() == pytest.approx(trip["t"]) and tr["t"][latched].max() < 0.035 + 1e-9
    assert fault.final_mode == "IDLE"
    kinds = [e["kind"] for e in fault.log]
    assert "start_rejected" in kinds
    rejected = next(e for e in fault.log if e["kind"] == "start_rejected")
    assert "precharge interlock" in rejected["detail"] and rejected["t"] == pytest.approx(0.036)
    assert any(e.get("to_mode") == "IDLE" and "reset accepted" in e["detail"] for e in fault.log)
    assert tr["v2"][-1] < 1.0
    assert fault.metrics["windows"]["output short circuit (0.3 Ohm)"]["mode_at_end"] == "FAULT"


def test_input_sag_trips_over_current_and_latch_holds(input_sag, design):
    assert len(input_sag.trips) == 1
    trip = input_sag.trips[0]
    assert trip["cause"] == "over_current_series_peak"
    assert trip["i_l_peak_A"] > design.protection.i_l_peak_trip_A
    assert 0.025 < trip["t"] < 0.027
    assert input_sag.final_mode == "FAULT"
    tr = input_sag.traces
    sag = (tr["t"] >= 0.025) & (tr["t"] < trip["t"])
    assert tr["phi_applied"][sag].max() > math.radians(40.0)  # the loop drove the phase shift towards its limit
    assert np.all(tr["enabled"][tr["t"] >= trip["t"]] == 0.0)
    assert np.all(tr["fault"][tr["t"] >= trip["t"]] == 1.0)
    assert tr["v1_bus"][sag].max() == pytest.approx(450.0)


def test_small_signal_response_matches_linear_discrete_model(design, controllers):
    """A small set-point step in the linear region follows the z-domain closed-loop model.

    The DF22 has b0 = 3.5 A/V, so a 2 V step would already command a 2.6 deg phase jump and engage the
    1 deg/period slew limiter; the check therefore uses a 0.5 V step, a relaxed slew limit and no quantiser.
    """
    d = replace(design, quantise=False, v_ref_slew_V_per_s=1e9, phi_slew_deg_per_update=5.0)
    r_full = d.v_ref ** 2 / d.nominal_power_W
    step_v = 0.5
    scenario = Scenario("linear-check", 0.046, 0.875 * d.v_ref, 4 * r_full, 0.0, [
        Event(0.0, "start", label="startup"), Event(0.010, "load_resistance", r_full, "full load"),
        Event(0.030, "setpoint", d.v_ref + step_v, "small step")])
    result = run_scenario(d, scenario)
    assert result.trips == [] and result.final_mode == "RUN"
    ctl = design_controllers(d)
    plant = DabSpsPlant(replace(d.plant, r_load=r_full), d.v_ref)
    phi0 = phase_shift_for_output_current(d.plant.v1, d.plant.n_ratio, d.plant.f_sw, d.plant.l_total, d.v_ref / r_full)
    k = output_current_gain(d.plant.v1, d.plant.n_ratio, d.plant.f_sw, d.plant.l_total, phi0)
    c_i = ctl.new_pi().transfer_function()
    c_v = ctl.new_df22().transfer_function()
    inner = (c_i * ZTransfer.gain(k).delayed(d.computation_delay_samples)).feedback(ZTransfer.delay(d.measurement_delay_samples))
    closed = (c_v * inner * plant.output_port_tf()).feedback()
    tr = result.traces
    mask = tr["t"] >= 0.030 - 1e-12
    v_sim = tr["v2"][mask]
    v_lin = d.v_ref + step_v * closed.step_response(v_sim.size + 1)[:-1]
    assert abs(v_sim[0] - d.v_ref) < 0.02  # settled before the step
    assert np.max(np.abs(v_sim - v_lin)) < 0.08 * step_v
    assert abs(v_sim[-1] - (d.v_ref + step_v)) < 0.01
    assert v_sim.max() > d.v_ref + step_v * 1.1  # the designed 60 deg phase-margin loop overshoots a reference step
    assert closed.is_stable()


def test_write_results_creates_json_hdf5_and_figures(tmp_path, design):
    summary = run_baseline(design, tmp_path, scenarios=("fault",), figures=True)
    assert (tmp_path / "summary.json").is_file() and (tmp_path / "traces_fault.h5").is_file()
    on_disk = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert on_disk["schema"] == "aipe-dab-sps-control-sim/0.1"
    assert on_disk["design_sha256"] == design.sha256() == summary["design_sha256"]
    assert on_disk["scenarios"]["fault"]["trips"][0]["cause"] == "under_voltage"
    assert on_disk["controllers"]["loops"]["voltage_loop_full_load"]["closed_loop_stable"] is True
    assert on_disk["model_assumptions"] and on_disk["limitations"]
    assert on_disk["modulator"]["tbprd_counts"] == 500.0
    ds = WaveformDataset.load_hdf5(tmp_path / "traces_fault.h5")
    assert ds.sha256() == on_disk["scenarios"]["fault"]["traces"]["dataset_sha256"]
    for channel in ("v2", "i2", "i_ref", "phi_applied", "mode", "gates_enabled", "fault_latched"):
        assert channel in ds, channel
    assert ds.channels["phi_applied"].unit == "rad" and ds.channels["v2"].unit == "V"
    assert ds.metadata["design_sha256"] == design.sha256()
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        assert on_disk["scenarios"]["fault"]["figure"] is None
    else:
        assert (tmp_path / "closed_loop_fault.png").is_file() and (tmp_path / "gate_pattern.png").is_file()
        assert on_disk["scenarios"]["fault"]["figure"].endswith("closed_loop_fault.png")


def test_design_validation_and_from_dict(design):
    bad = replace(design, f_c_voltage_Hz=5000.0)
    assert any("f_c_voltage < f_c_current" in p for p in bad.validate())
    with pytest.raises(ValueError, match="invalid control design"):
        design_controllers(bad)
    assert replace(design, i_ref_limit_A=1e3).validate()
    assert replace(design, protection=ProtectionLimits(v2_under_V=450.0)).validate()
    assert replace(design, plant=DabSpsPlantParameters(ts=1e-6)).validate()
    data = json.loads(json.dumps(design.to_dict()))
    back = ControlDesign.from_dict(data)
    assert back == design and back.sha256() == design.sha256()
    with pytest.raises(ValueError, match="unknown"):
        ControlDesign.from_dict({"foo": 1})
    with pytest.raises(ValueError, match="unknown"):
        ControlDesign.from_dict({"plant": {"bar": 2}})


def test_zero_computation_delay_option_gains_phase(design):
    ideal = design_controllers(replace(design, computation_delay_samples=0))
    real = design_controllers(design)
    pm_ideal = ideal.report["loops"]["current_loop_nominal"]["phase_margin_deg"]
    pm_real = real.report["loops"]["current_loop_nominal"]["phase_margin_deg"]
    assert pm_ideal > pm_real + 5.0
    result = run_scenario(replace(design, computation_delay_samples=0), "fault", ideal)
    assert result.trips and result.trips[0]["cause"] == "under_voltage"


def test_format_comparison_table_renders_rows():
    synthetic = {"rows": [{"phi_deg": 22.5, "p_plant_W": 10000.0, "p2_ngspice_W": 9995.5, "rel_err_p2": -4.5e-4, "p1_ngspice_W": 10001.0,
                           "rel_err_p1": 1e-4, "i_l_rms_plant_A": 13.678, "i_l_rms_ngspice_A": 13.680, "rel_err_i_l_rms": 1.8e-4,
                           "phi_measured_deg": 22.5, "status": "steady_state"},
                          {"phi_deg": 35.0, "p_plant_W": 14321.0, "p2_ngspice_W": None, "rel_err_p2": None, "p1_ngspice_W": None,
                           "rel_err_p1": None, "i_l_rms_plant_A": 20.732, "i_l_rms_ngspice_A": None, "rel_err_i_l_rms": None,
                           "phi_measured_deg": None, "status": "solver_failed"}],
                 "ngspice": {"version": "47", "platform": "test"}, "sim_settings": {"cycles": 12, "max_step_fraction": 200},
                 "level1_model_note": "note"}
    text = format_comparison_table(synthetic)
    lines = text.splitlines()
    assert lines[0].startswith("| phi (deg) |") and len([l for l in lines if l.startswith("| ") and "steady_state" in l]) == 1
    assert "| 35 | 14321.0 | n/a | n/a |" in text and "-0.045" in text and "solver_failed" in text
