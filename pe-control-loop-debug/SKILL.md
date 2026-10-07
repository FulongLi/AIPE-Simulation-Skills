---
name: pe-control-loop-debug
description: Use this skill for power electronics control-loop simulation and debugging, especially PLECS or LTspice workflows involving loop stability, compensation, transient response, oscillation diagnosis, Bode plots, sampling delay, PWM effects, simulation convergence, and waveform-based root cause analysis.
---

# Power Electronics Control-Loop Simulation And Debugging

## Accessibility

Tool and hardware access depends on the chosen execution variant. Python averaged analysis reduces fidelity; preserve requested switching-tool diagnosis.
For the scoped open path, see `../pe-python-control-analysis/SKILL.md` when available in the collection.

## Goal

Use this skill when helping power electronics engineers diagnose control-loop simulation and debugging problems. Prefer executable checks, key waveforms, and next experiments over generic control theory explanations.

This first version focuses on control-loop simulation and debugging. It does not cover magnetics design, thermal design, EMI, component selection, or the full hardware bring-up workflow.

## Classify The Problem First

When the user provides a topology, control method, waveform, simulation description, or fault symptom, first classify the issue into one or more categories:

- Stability: insufficient phase margin, excessive crossover frequency, right-half-plane zero, resonance peak, or subharmonic oscillation.
- Compensation parameters: misplaced zeros/poles, excessive integral action, low bandwidth, or missing worst-case input/load coverage.
- Sampling and delay: ADC sample timing, ZOH, computation delay, PWM update timing, or digital filter phase lag.
- Model setup: averaged model versus switching model mismatch, initial conditions, parasitics, control saturation, or soft-start.
- Power-stage parameters: LC resonance, ESR zero, capacitor tolerance, inductor saturation, or load model.
- Simulation credibility: time step, convergence, probe location, loop injection method, perturbation amplitude, or measurement script.

## Ask Only For Critical Missing Inputs

Continue the diagnosis when possible. Ask follow-up questions only when the missing input could change the conclusion:

- Topology and operating mode: Buck, Boost, LLC, flyback, inverter, CCM, DCM, CRM, and related modes.
- Control method: voltage mode, peak current mode, average current mode, digital control, PLL, and similar loops.
- Key parameters: switching frequency, input/output range, L/C/ESR, load range, compensation network, or digital controller parameters.
- Simulation setup: PLECS/LTspice, averaged or switching model, transient/Bode/sweep, perturbation location and amplitude.
- Abnormal symptom: oscillation frequency, operating condition, key waveforms, current limit, saturation, or duty-cycle rail.

## Reference Selection

Load only the references needed for the task:

- PLECS modeling, sweeps, Bode, and transient checks: `references/plecs-workflow.md`
- LTspice small-signal, transient, convergence, and loop injection: `references/ltspice-workflow.md`
- Control-loop diagnosis checklist: `references/control-loop-checklist.md`
- Anonymized project case capture: `references/anonymous-case-template.md`

## Default Answer Structure

When answering a control-loop debugging request, use this structure by default:

1. Problem restatement: restate the symptom, operating condition, and known constraints in engineering language.
2. Ranked hypotheses: rank likely root causes by probability and risk, with the evidence needed for each.
3. Suggested simulation checks: provide executable PLECS/LTspice checks, sweeps, or comparison experiments.
4. Key waveforms: list the voltages, currents, error signals, duty command, limit flags, and sample points to inspect.
5. Parameter or compensation suggestions: explain the proposed change, expected effect, and constraints.
6. Next experiment: give the smallest closed-loop action that can quickly reject or confirm a hypothesis.

## Capturing Project Experience

When the user asks to summarize project experience, postmortems, or cases, use the anonymized case format. Preserve topology, symptom, diagnosis path, evidence, root cause, and reusable rules. Remove customer names, project codenames, product names, exact confidential parameters, internal paths, and any non-public information.
