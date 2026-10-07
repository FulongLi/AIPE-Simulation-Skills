---
name: pe-simetrix-simplis-power-electronics
description: Use this skill for SIMetrix and SIMPLIS power electronics simulation workflows, especially converter switching simulation, fast transient analysis, control-loop validation, double-pulse test setup, MOSFET/IGBT/diode model checks, gate-drive behavior, parasitic sensitivity, convergence debugging, and waveform credibility review.
---

# SIMetrix/SIMPLIS Power Electronics Simulation

## Accessibility

This optional variant requires an external commercial tool licence. Piecewise-linear periodic operating-point capability is not guaranteed in ngspice.
For the scoped open path, see `../pe-ngspice-switching-validation/SKILL.md` when available in the collection.

## Goal

Use this skill as an expert workflow for SIMetrix and SIMPLIS power electronics simulation. It focuses on converter-level switching behavior, fast transient analysis, double-pulse tests, device stress, control-loop validation, and simulation credibility.

Prefer actionable simulation checks, waveform probes, model simplification, and root-cause isolation over generic circuit theory.

## Classify The Simulation Task

When a request arrives, first classify it:

- Converter switching simulation: Buck, Boost, flyback, forward, LLC, phase-shift full bridge, PFC, inverter, synchronous rectification, or clamp/snubber behavior.
- SIMPLIS fast transient model: piecewise-linear switching model, cycle-by-cycle behavior, startup, load step, line step, and control-loop response.
- SIMetrix SPICE-level model: semiconductor switching detail, parasitic ringing, gate-drive behavior, reverse recovery, and convergence-sensitive transient analysis.
- Double-pulse test: MOSFET/IGBT/SiC/GaN switching loss, diode reverse recovery, gate resistance, DC-link parasitic inductance, voltage overshoot, and measurement timing.
- Control-loop validation: AC loop gain, POP/PAC-style steady-state analysis where available, compensation tuning, and transient cross-check.
- Simulation credibility issue: time step, convergence, initial condition, device model validity, parasitic assumptions, probe location, and mismatch with bench waveforms.

## Ask For Missing Inputs

Ask only for information that materially changes the diagnosis:

- Topology, device technology, switching frequency, input/output range, load range, and operating mode.
- Whether the model uses SIMetrix SPICE, SIMPLIS, or a mixed workflow.
- Target result: startup, load step, loop gain, device stress, switching loss, double-pulse waveform, or fault reproduction.
- Device and gate-drive details: MOSFET/IGBT/diode model source, gate resistance, driver voltage/current, dead time, snubber, package and layout parasitics.
- Simulation setup: transient command, maximum time step, initial conditions, POP/PAC or AC setup, probe location, and abnormal waveform.

## References

Load only what is needed:

- Converter and SIMPLIS transient workflow: `references/converter-simplis-workflow.md`
- Double-pulse test workflow: `references/double-pulse-test-workflow.md`
- Device model, gate-drive, and parasitic checklist: `references/device-gate-parasitic-checklist.md`
- Convergence and waveform credibility checklist: `references/convergence-waveform-checklist.md`

## Default Answer Structure

1. Simulation target restatement: state the converter, operating condition, tool path, and trusted quantity.
2. Recommended SIMetrix/SIMPLIS setup: identify whether SPICE-level SIMetrix, SIMPLIS, or both should be used.
3. Modeling assumptions: list device models, parasitics, gate-drive behavior, control model, initial conditions, and measurement points.
4. Checks to run: propose model simplification, time-step checks, parasitic sweeps, gate-resistance sweeps, double-pulse variants, or loop/transient cross-checks.
5. Key waveforms and metrics: list gate voltage, drain/collector voltage, switch current, diode current, inductor current, output voltage, control signal, overshoot, ringing frequency, and switching energy.
6. Credibility verdict: state what can be trusted, what is only directional, and the smallest next validation action.
