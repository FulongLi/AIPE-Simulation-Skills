# AIPE — Simulation Skills

AIPE Simulation Skills is the simulation workflow collection of **AI for Power Engineering**. It pairs
13 agent skills - procedural `SKILL.md` workflows for circuit, control, CAD, PCB and field-analysis
tools - with an installable Python package, `aipe_simulation`, that executes real ngspice experiments and
analyses the resulting waveforms. Open-source tools (ngspice, python-control, FreeCAD, KiCad, Gmsh/Elmer)
are the default path; LTspice, PLECS, MATLAB/Simulink, SIMetrix/SIMPLIS, ANSYS and COMSOL remain optional,
externally licensed integrations. Contracts come from AIPE-Core; the manifest is indexed by AIPE-Registry.

## Features

- 13 skills with maturity and tool-access classification in `skills.json`; procedures live in each
  skill's `references/`
- `aipe_simulation.ngspice`: locates and qualifies ngspice, runs batch netlists, parses raw files
- `aipe_simulation.dab`: typed `DabCircuitSpec`, single-phase-shift gating, ideal (Level 1) and behavioural
  (Level 2) dual-active-bridge netlists, runner writing netlist, log, raw data, HDF5 waveforms and
  `summary.json`
- `aipe_simulation.waveforms`: HDF5 waveform dataset, steady-state detection, RMS/peak/power metrics,
  per-switch turn-off currents, ZVS conditions, volt-second and energy balances
- `aipe_simulation.control`: host-side single-phase-shift control baseline verified against ngspice runs
- Deterministic README generation and skill validation enforced in CI

## Installation

Python 3.10 or newer; numpy, h5py and PyYAML are installed with the package. ngspice is optional (solver
tests skip without it). The open control example needs `pe-python-control-analysis/requirements.txt`.

```sh
python -m pip install -e ".[dev]"
python -m pip install -r pe-python-control-analysis/requirements.txt
```

## Usage

```sh
aipe-sim doctor                                   # locate and numerically qualify ngspice
aipe-sim dab run --out runs/dab-level1            # ideal 10 kW DAB: netlist, ngspice run, HDF5 waveforms, summary.json
python pe-python-control-analysis/scripts/buck_control.py --output buck-result.json
python -m pytest -q tests/                        # solver tests skip when ngspice is absent
```

To use a skill in Codex, copy its folder into your skills directory and invoke it by name, for example
`Use $pe-ngspice-switching-validation to check this switching netlist`; see
[docs/development.md](docs/development.md).

## Skill catalogue

| Skill | Maturity | Access | Focus | References |
| --- | --- | --- | --- | ---: |
| [`pe-ansys-electromagnetic-thermal`](./pe-ansys-electromagnetic-thermal/SKILL.md) | usable | commercial | ANSYS Electromagnetic And Thermal Simulation For Power Electronics | 4 |
| [`pe-comsol-electromagnetic-thermal`](./pe-comsol-electromagnetic-thermal/SKILL.md) | usable | commercial | COMSOL Electromagnetic And Thermal Simulation For Power Electronics | 4 |
| [`pe-control-loop-debug`](./pe-control-loop-debug/SKILL.md) | usable | mixed | Power Electronics Control-Loop Simulation And Debugging | 4 |
| [`pe-dsp-fpga-control-debug`](./pe-dsp-fpga-control-debug/SKILL.md) | usable | target-dependent | DSP And FPGA Power Electronics Control Debugging | 4 |
| [`pe-freecad-converter-packaging`](./pe-freecad-converter-packaging/SKILL.md) | scaffold | open_source | Converter Mechanical Packaging with FreeCAD | 1 |
| [`pe-kicad-power-stage-review`](./pe-kicad-power-stage-review/SKILL.md) | scaffold | open_source | Power-Stage PCB Review with KiCad | 1 |
| [`pe-ltspice-power-electronics`](./pe-ltspice-power-electronics/SKILL.md) | usable | free_proprietary | LTspice Power Electronics Simulation | 3 |
| [`pe-ngspice-switching-validation`](./pe-ngspice-switching-validation/SKILL.md) | usable | open_source | Switching Circuit Validation with ngspice | 1 |
| [`pe-open-fea-problem-setup`](./pe-open-fea-problem-setup/SKILL.md) | scaffold | open_source | Open Field-Analysis Problem Setup | 1 |
| [`pe-plecs-power-electronics`](./pe-plecs-power-electronics/SKILL.md) | usable | commercial | PLECS Power Electronics Simulation | 4 |
| [`pe-python-control-analysis`](./pe-python-control-analysis/SKILL.md) | prototype | open_source | Converter Averaged Control Analysis | 1 |
| [`pe-simetrix-simplis-power-electronics`](./pe-simetrix-simplis-power-electronics/SKILL.md) | usable | commercial | SIMetrix/SIMPLIS Power Electronics Simulation | 4 |
| [`pe-simulink-power-electronics`](./pe-simulink-power-electronics/SKILL.md) | usable | commercial | MATLAB/Simulink Power Electronics Simulation | 3 |

## Project Information

- Version: 0.2.0 (`pyproject.toml`, package `aipe-simulation-skills`)
- Status: Alpha (package classifier `Development Status :: 3 - Alpha`; `aipe.yaml` maturity `usable`).
  CAD, PCB and FEA skills are scaffolds, MCP connectors are evaluated only, no hardware validation is claimed
- Developer: Fulong Li
- Organisation: Spirit Connect / AIPE Labs
- License: not declared - no licence file; `aipe.yaml` records `NOASSERTION` and the retained skill content
  has no blanket licence

## Documentation

- [Using and adding skills, conventions, README regeneration and CI](docs/development.md)
- [Architecture: package modules, skill layout and CLI](docs/architecture.md)
- [Executed 10 kW DAB benchmark and model lessons](docs/dab-models.md) ·
  [SPS control specification](docs/dab-sps-control-spec.md)
- [Tool policy and capability matrix](docs/tool-policy.md) · [v0.1 validation record](docs/validation.md) ·
  [Core mapping](docs/core-mapping.md)
- [Skill metadata](skills.json) · [Capability manifest](aipe.yaml)
