"""Synthetic ideal CCM buck linear analysis; no hardware/performance claim."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import platform

import control
import numpy as np
import scipy


def analyse(vin=48.0, inductance=100e-6, capacitance=100e-6, resistance=10.0, gain=0.02):
    values = (vin, inductance, capacitance, resistance, gain)
    if any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("Inputs must be finite positive SI values")
    plant = control.tf([vin], [inductance * capacitance, inductance / resistance, 1])
    loop = gain * plant
    closed = control.feedback(loop, 1)
    poles = control.poles(closed)
    stable = bool(np.all(poles.real < 0))
    if not stable:
        raise ValueError("Example loop is unstable; refuse misleading step summary")
    duration = 12 / float(np.min(-poles.real))
    times, response = control.step_response(closed, np.linspace(0, duration, 4001))
    omega = 2 * math.pi * 100
    value = complex(control.evalfr(plant, 1j * omega))
    return {
        "schema_version": "0.1.0", "kind": "analytical", "model": "ideal-ccm-buck-linear",
        "tools": {"python": platform.python_version(), "python-control": control.__version__, "numpy": np.__version__, "scipy": scipy.__version__},
        "inputs": {"input_voltage": {"value": vin, "unit": "V"}, "inductance": {"value": inductance, "unit": "H"}, "capacitance": {"value": capacitance, "unit": "F"}, "load_resistance": {"value": resistance, "unit": "Ohm"}, "proportional_gain": {"value": gain, "unit": "1/V"}},
        "results": {"plant_dc_gain": {"value": float(control.dcgain(plant)), "unit": "V"}, "closed_loop_dc_gain": {"value": float(control.dcgain(closed)), "unit": "1"}, "final_unit_reference_response": {"value": float(response[-1]), "unit": "1"}, "frequency": {"value": 100, "unit": "Hz"}, "plant_magnitude": {"value": abs(value), "unit": "V"}, "plant_phase": {"value": math.atan2(value.imag, value.real), "unit": "rad"}, "stable_linear_poles": stable},
        "assumptions": ["Synthetic ideal CCM buck", "Zero ESR and ideal continuous modulator", "Unity voltage feedback and proportional compensation", "Linear perturbation model; excludes switching ripple, delay, saturation and startup"],
        "validation": {"status": "analytical_only", "measured": False, "limitations": ["Model-specific numerical regression only; no hardware or switched-model validation"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(analyse(), indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
