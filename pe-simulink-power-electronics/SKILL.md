---
name: pe-simulink-power-electronics
description: Use this skill for MATLAB and Simulink power electronics simulation workflows, including Simscape Electrical modeling, switching and averaged converter models, control-loop co-simulation, solver setup, parameter sweeps, waveform validation, and debugging unreliable simulation results.
---

# MATLAB/Simulink Power Electronics Simulation

## Accessibility

This optional variant requires an external commercial tool licence. Python/Octave can cover numerical/control analysis; block semantics and code generation require separate migration.
For the scoped open path, see `../pe-python-control-analysis/SKILL.md` when available in the collection.

## Goal

Use this skill to plan, build, inspect, and debug power electronics simulations in MATLAB, Simulink, and Simscape Electrical. The priority is to make the model verifiable, sweepable, and reproducible.

## Classify The Simulation Type

When a request arrives, first classify it:

- Switching power-stage model: device behavior, PWM, sampling, switching ripple, parasitics, and solver stability.
- Averaged model: controller design, transfer functions, operating-point sweeps, loop stability, and fast iteration.
- Control co-simulation: discrete control, sample time, PWM update, delay, saturation, and anti-windup.
- System-level simulation: upstream/downstream source and load, DC link, motor drive or inverter, protection state machine, and operating coverage.
- Model credibility issue: solver, time step, initial conditions, units, parameter source, and waveform measurement location.

## Ask For Missing Inputs

Ask only for information that changes the modeling strategy or diagnosis:

- Topology, power-stage parameters, input/output range, and load type.
- Whether the model uses Simscape Electrical, Specialized Power Systems, or pure Simulink blocks.
- Whether the goal is switching detail, averaged control design, system-level behavior, or pre-code-generation validation.
- Controller sample time, PWM frequency, and continuous/discrete implementation style.
- Current abnormal waveform, solver settings, maximum step size, algebraic loop, or convergence error.

## References

Load only what is needed:

- Modeling and solver setup: `references/modeling-solver-workflow.md`
- Control co-simulation and parameter sweeps: `references/control-sweep-workflow.md`
- Model credibility checklist: `references/simulink-validation-checklist.md`

## Default Answer Structure

1. Simulation target restatement: clarify whether the user is validating the power stage, controller, system behavior, or a fault.
2. Recommended model level: state whether to use a switching model, averaged model, or both.
3. Simulink/Simscape settings: suggest solver, step size, initialization, sample time, and measurement points.
4. Check experiments: propose sweeps, load steps, input perturbations, controller comparisons, or model simplification experiments.
5. Key waveforms and metrics: list the signals and pass/fail criteria that must be recorded.
6. Next step: provide the smallest executable action that can quickly validate model credibility.
