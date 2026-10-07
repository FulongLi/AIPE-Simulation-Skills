---
name: pe-ltspice-power-electronics
description: Use this skill for LTspice power electronics simulation workflows, including switching converter transient analysis, averaged models, loop-gain injection, compensation validation, convergence debugging, device model sanity checks, and waveform-based diagnosis.
---

# LTspice Power Electronics Simulation

## Accessibility

This optional variant uses free proprietary LTspice. Validate device models and dialect compatibility before translating to ngspice.
For the scoped open path, see `../pe-ngspice-switching-validation/SKILL.md` when available in the collection.

## Goal

Use this skill to build, inspect, and debug LTspice simulations for power supplies and power converters. The priority is to make simulation results credible, reproducible, and useful for engineering decisions.

## Classify The Task First

- Switching transient simulation: startup, load step, switching node, inductor current, current limit, and device stress.
- Averaged model or small-signal analysis: loop gain, compensation network, crossover frequency, and phase margin.
- Convergence issue: ideal components, parasitics, initial conditions, solver behavior, and model physicality.
- Device model issue: MOSFET, diode, op amp, comparator, or controller macro-model suitability.
- Waveform diagnosis: infer whether an abnormal frequency, node, or operating point indicates a control, power-stage, or numerical issue.

## Ask For Missing Inputs

Ask only for inputs that materially change the diagnosis:

- Topology, control method, switching frequency, input/output range, and load range.
- Whether the model is a switching model or averaged model, and whether the target is transient, AC, or loop measurement.
- Abnormal waveform, simulation directive, maximum time step, initial conditions, and error message.
- Critical model source: controller macro-model, MOSFET/diode model, op amp, or comparator model.

## References

Load only what is needed:

- Transient and waveform diagnosis: `references/transient-waveform-workflow.md`
- Loop-gain injection and compensation validation: `references/loop-gain-workflow.md`
- Convergence and model credibility: `references/convergence-model-checklist.md`

## Default Answer Structure

1. Target and symptom: state the operating condition, abnormal behavior, and available evidence.
2. Credibility check: say whether the current simulation result is trustworthy and what checks are missing.
3. LTspice actions: provide directives, probes, comparison experiments, or model simplification steps.
4. Key waveforms: list the nodes and control signals that must be inspected together.
5. Ranked root-cause hypotheses: classify them as control-loop, power-stage, device-model, or numerical setup issues.
6. Next experiment: give the fastest action that can eliminate one hypothesis.
