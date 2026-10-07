---
name: pe-comsol-electromagnetic-thermal
description: Use this skill for COMSOL-based power electronics electromagnetic and thermal simulation workflows, including magnetic component modeling, current-density and loss analysis, heat-transfer and multiphysics coupling, material and boundary-condition setup, mesh refinement, parameter sweeps, and simulation credibility review.
---

# COMSOL Electromagnetic And Thermal Simulation For Power Electronics

## Accessibility

This optional variant requires an external commercial tool licence. Open field solvers need a separately justified model; no one-to-one multiphysics replacement claimed.
For the scoped open path, see `../pe-open-fea-problem-setup/SKILL.md` when available in the collection.

## Goal

Use this skill as an expert workflow for COMSOL electromagnetic, thermal, and multiphysics simulation in power electronics. It is intended for magnetic components, busbars, PCB copper, power modules, heatsinks, and coupled loss-to-temperature studies where model credibility depends on physics selection, material data, mesh, boundary conditions, and validation.

## Classify The Simulation Task

When a request arrives, first classify the task:

- Electromagnetic field study: flux density, inductance, leakage flux, current density, eddy current, proximity effect, or saturation.
- Loss modeling: copper loss, core loss, busbar loss, PCB copper loss, shield loss, or semiconductor/module heat source.
- Thermal study: winding/core/module temperature, heatsink performance, cold plate, natural/forced convection, and transient warm-up.
- Multiphysics coupling: electromagnetic losses feeding heat transfer, temperature-dependent conductivity/permeability, or iterative electro-thermal analysis.
- Parameter sweep or optimization: geometry, air gap, conductor layout, material grade, cooling condition, frequency, and current waveform.
- Credibility review: physics interface choice, mesh, material validity, boundary conditions, solver settings, and mismatch with measurements.

## Ask For Missing Inputs

Ask only for information that changes the model setup or credibility judgment:

- Hardware: inductor, transformer, busbar, PCB copper, power module, heatsink, cold plate, enclosure, or complete assembly.
- Operating point: current waveform, frequency spectrum, DC bias, RMS/peak current, ambient, airflow, coolant, duty cycle, and thermal limit.
- COMSOL physics: Magnetic Fields, Magnetic Fields No Currents, Electric Currents, Heat Transfer, CFD, or multiphysics coupling.
- Material data: B-H curve, core-loss model, conductivity versus temperature, thermal conductivity, convection assumptions, and contact resistance.
- Validation data: inductance, resistance, impedance, loss, temperature rise, thermal image, or thermocouple data.

## References

Load only what is needed:

- Electromagnetic modeling workflow: `references/em-modeling-workflow.md`
- Thermal and multiphysics coupling workflow: `references/thermal-multiphysics-workflow.md`
- Materials, boundaries, mesh, and sweep checklist: `references/materials-boundaries-mesh-sweep-checklist.md`
- Credibility review and reporting checklist: `references/comsol-validation-reporting-checklist.md`

## Default Answer Structure

1. Simulation target restatement: define the trusted quantity, operating condition, and acceptable accuracy.
2. Recommended COMSOL workflow: identify physics interfaces, model dimension, study type, coupling method, and required fidelity.
3. Modeling assumptions: list geometry simplifications, materials, excitations, thermal boundaries, mesh strategy, and coupling assumptions.
4. Checks to run: propose mesh refinement, material sensitivity, boundary sensitivity, parameter sweeps, power balance, and measurement comparison.
5. Key outputs: list inductance, resistance, flux density, current density, loss breakdown, temperature rise, hot spots, and thermal path.
6. Credibility verdict: state what can be trusted, what is directional only, and the minimum next validation action.
