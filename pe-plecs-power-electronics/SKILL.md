---
name: pe-plecs-power-electronics
description: Use this skill for PLECS power electronics simulation workflows, including switching and averaged converter models, control-loop analysis, Bode and parameter sweeps, thermal and loss modeling, solver setup, waveform validation, and debugging unreliable PLECS results.
---

# PLECS Power Electronics Simulation

## Accessibility

This optional variant requires an external commercial tool licence. ngspice and Python cover reduced circuit/control experiments; event solvers, thermal libraries and code generation differ.
For the scoped open path, see `../pe-ngspice-switching-validation/SKILL.md` when available in the collection.

## Goal

Use this skill to plan, build, inspect, and debug PLECS simulations for power electronics systems. The priority is to make the model fast enough for engineering iteration, detailed enough for the target question, and credible enough to support design decisions.

## Classify The Simulation Type

When a request arrives, first classify it:

- Switching power-stage model: PWM behavior, switching ripple, device stress, current limit, protection, and nonlinear control behavior.
- Averaged model: loop design, operating-point sweeps, fast control iteration, and system-level stability checks.
- Control-loop analysis: loop injection, Bode plots, compensation tuning, sampling delay, PWM update, and transient response.
- Loss and thermal simulation: semiconductor losses, magnetic losses, heatsink or thermal-network behavior, and temperature-dependent stress.
- Model credibility issue: solver settings, initialization, step size, event handling, model level mismatch, or questionable waveforms.

## Ask For Missing Inputs

Ask only for information that materially changes the simulation strategy or diagnosis:

- Topology, power rating class, switching frequency, input/output range, load range, and operating mode.
- Whether the model is switching, averaged, thermal, or a mixed model.
- Controller type, sample time, PWM update behavior, saturation limits, and protection logic.
- Target output: transient waveform, loop stability, parameter sweep, loss estimate, thermal rise, or fault reproduction.
- Current abnormal waveform, PLECS solver settings, initialization method, and any warnings or convergence symptoms.

## References

Load only what is needed:

- Model architecture and solver setup: `references/modeling-solver-workflow.md`
- Control-loop, Bode, and sweep workflow: `references/control-bode-sweep-workflow.md`
- Loss and thermal simulation workflow: `references/loss-thermal-workflow.md`
- Simulation credibility checklist: `references/plecs-validation-checklist.md`

## Default Answer Structure

1. Simulation target restatement: clarify whether the user is validating the power stage, controller, loss/thermal behavior, or a fault.
2. Recommended model level: state whether to use a switching model, averaged model, thermal model, or staged combination.
3. PLECS setup: suggest solver, step size, initialization, sample times, event handling, and measurement points.
4. Check experiments: propose load steps, input perturbations, Bode checks, parameter sweeps, model simplification, or thermal operating points.
5. Key waveforms and metrics: list the signals, limits, and pass/fail criteria that must be recorded.
6. Next step: provide the smallest executable PLECS action that can validate the model or reject a root-cause hypothesis.
