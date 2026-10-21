---
name: pe-ngspice-switching-validation
description: Build and check open ngspice switching-circuit experiments for converter waveforms, operating points and transient convergence, using the executable aipe_simulation package (dual-active-bridge generator, waveform analysis engine). Use for netlist-based circuit simulation; averaged-loop analysis and production-qualified device models require separate evidence.
---

# Switching Circuit Validation with ngspice

Prefer ngspice batch netlists for an open reproducible circuit experiment. Keep
LTspice, PLECS or SIMPLIS when requested or when a required model/dedicated solver
needs that tool; model dialects and loss-model fidelity are not interchangeable.

## Executable path (`aipe_simulation`)

This repository ships a Python package (`pip install -e .`) that turns the
procedure below into executed, reproducible runs:

```sh
aipe-sim doctor                                   # locate ngspice and run the RC qualification test
aipe-sim dab default-spec > dab.yaml              # typed DabCircuitSpec in SI units
aipe-sim dab run --spec dab.yaml --out runs/dab   # netlist -> ngspice -> HDF5 waveforms -> summary.json
aipe-sim dab analyse --run runs/dab               # recompute metrics from the stored dataset
```

`aipe_simulation.dab` generates the dual-active-bridge model (Level 1 ideal,
Level 2 behavioural with dead time, Coss, body-diode fit, DC-link parasitics and
RC port), `aipe_simulation.ngspice` runs the solver and parses raw files, and
`aipe_simulation.waveforms` identifies the periodic steady state and computes
RMS/peak currents, port powers, per-switch turn-off currents and ZVS conditions,
volt-second balance, capacitor drift and an energy balance. Read
`docs/dab-models.md` for conventions, executed benchmark numbers and the
numerical lessons (operating point skipping, Coss damping, local decoupling,
behavioural channel) that the models encode.

## Manual procedure

Establish topology, boundary conditions, drive waveform, model provenance and
the specific waveform/question being tested. Identify any missing device models
before interpreting losses, switching stress or efficiency.

The self-contained `assets/ideal-buck.cir` models a 48 V buck at 100 kHz with an
ideal switch/diode. Run in a writable scratch folder:

```sh
ngspice -b -o buck.log /absolute/path/to/assets/ideal-buck.cir
```

Read `references/convergence.md` for timestep and steady-state checks. Compare
late-window mean output with `D Vin`, and repeat with half the maximum timestep.
The smoke check's broad 23–25 V interval catches setup failures; it is not a
specification, calibrated loss estimate or proof of numerical convergence.

Preserve netlist, solver version, log, all warnings, time-window definitions and
waveform artifacts. Diagnose failed convergence instead of relaxing tolerances
until the answer looks right. Distinguish configured, completed and failed runs;
never fill in results for a solver that was not executed.

Report schematic/netlist assumptions, units, model licences, tests and remaining
uncertainties. A vendor model requires its own usage/distribution review; an open
simulator does not relicense model files. No connector is required.
