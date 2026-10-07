---
name: pe-ansys-electromagnetic-thermal
description: Use this skill for ANSYS-based power electronics electromagnetic and thermal simulation workflows, including Maxwell electromagnetic modeling, winding and busbar loss extraction, magnetic component loss validation, Icepak or Mechanical thermal coupling, mesh/material setup, boundary-condition review, and simulation credibility checks.
---

# ANSYS Electromagnetic And Thermal Simulation For Power Electronics

## Accessibility

This optional variant requires an external commercial tool licence. Elmer/GetDP/CalculiX/openEMS only for suitable physics; specialised features and material databases may differ.
For the scoped open path, see `../pe-open-fea-problem-setup/SKILL.md` when available in the collection.

## Goal

Use this skill as an expert workflow for ANSYS electromagnetic and thermal simulation in power electronics. It is intended for magnetic components, busbars, power modules, heatsinks, and coupled loss-to-temperature studies where simulation credibility depends on geometry simplification, material data, boundary conditions, mesh quality, and validation against electrical or thermal measurements.

## Classify The Simulation Task

When a request arrives, first classify the task:

- Electromagnetic loss extraction: winding loss, core loss, busbar loss, eddy current loss, proximity effect, or current sharing.
- Magnetic component design check: inductor, transformer, coupled inductor, planar magnetics, gap fringing, leakage inductance, and saturation margin.
- Power interconnect study: busbar, laminated busbar, current crowding, stray inductance, loop area, and AC loss.
- Thermal simulation: device junction/case/heatsink temperature, winding temperature, core temperature, forced or natural convection, and enclosure effects.
- Coupled electro-thermal workflow: EM loss map imported into Icepak or Mechanical, temperature-dependent material update, and iteration.
- Credibility review: material assumptions, mesh density, boundary conditions, symmetry, solver settings, or mismatch with measurement.

## Ask For Missing Inputs

Ask only for information that changes the simulation setup or credibility judgment:

- Target hardware: inductor, transformer, busbar, power module, PCB copper, heatsink, enclosure, or complete assembly.
- Operating condition: frequency, current waveform, RMS/peak current, DC bias, duty cycle, switching frequency, ambient, airflow, and thermal limit.
- ANSYS tool chain: Maxwell 2D/3D, Q3D Extractor, Icepak, Mechanical, Electronics Desktop, Workbench coupling, or exported loss tables.
- Material data: B-H curve, core-loss model, conductivity versus temperature, Litz/foil/copper geometry, insulation, thermal conductivity, TIM, and convection assumptions.
- Validation data: measured inductance, resistance, loss, temperature rise, thermal impedance, or waveform data.

## References

Load only what is needed:

- Maxwell electromagnetic modeling workflow: `references/maxwell-em-workflow.md`
- Loss extraction and coupled thermal workflow: `references/loss-thermal-coupling-workflow.md`
- Materials, mesh, and boundary-condition checklist: `references/materials-mesh-boundaries-checklist.md`
- Credibility review and reporting checklist: `references/ansys-validation-reporting-checklist.md`

## Default Answer Structure

1. Simulation target restatement: state what physical quantity must be trusted and at which operating point.
2. Recommended ANSYS workflow: identify Maxwell/Q3D/Icepak/Mechanical flow and the model fidelity needed.
3. Modeling assumptions: list geometry simplifications, material models, excitations, thermal boundaries, and coupling assumptions.
4. Checks to run: propose mesh refinement, material sensitivity, boundary sensitivity, loss balance, and measurement cross-checks.
5. Key outputs: list inductance, resistance, loss breakdown, flux density, current density, hot spots, thermal resistance, and temperature rise.
6. Credibility verdict: state what can be trusted, what cannot yet be trusted, and the smallest next validation action.
