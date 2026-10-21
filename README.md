# AIPE Simulation Skills

AIPE means **AI for Power Engineering**. This repository translates engineering questions into reusable simulation, CAD, PCB and field-analysis workflows. Open-source tools are the default learning path; commercial workflows remain optional professional integrations.

All eight existing workflows and their reference material are retained. Five new engineering workflows add Python control analysis, ngspice switching validation, FreeCAD packaging, KiCad power-stage review and open field-analysis problem setup. LTspice is free proprietary software. PLECS, MATLAB/Simulink, SIMetrix/SIMPLIS, ANSYS and COMSOL require external licences for their respective variants.

The [tool policy and capability matrix](docs/tool-policy.md), [skill metadata](skills.json), [AIPE manifest](aipe.yaml), and [Core mapping](docs/core-mapping.md) describe exact boundaries. CAD/PCB/FEA additions are workflow scaffolds; MCP candidates are researched only. Existing repository content has no declared blanket licence and remains `NOASSERTION`.

## Runnable Open Example

Create an isolated Python environment, install `pe-python-control-analysis/requirements.txt`, and run:

```sh
python pe-python-control-analysis/scripts/buck_control.py --output buck-result.json
python -m unittest discover -s tests -v
```

The synthetic averaged buck example checks numerical behaviour with python-control; it claims no hardware validation. An ngspice netlist is included and exercised in Ubuntu CI; solver-dependent local tests explicitly skip when ngspice is absent.

## Executable Simulation Package (`aipe_simulation`)

Besides the procedural skills, this repository ships an installable Python package
(`python -m pip install -e .`) that executes real ngspice experiments:

- `aipe_simulation.ngspice`: locate ngspice (PATH, `AIPE_NGSPICE`, `AIPE_TOOLS_DIR`, portable
  Windows builds), qualify it with an RC step-response test, run batch netlists and parse raw files.
- `aipe_simulation.dab`: typed `DabCircuitSpec` (SI units), single-phase-shift gate timing for all
  eight switches, ngspice netlists for the ideal (Level 1) and behavioural (Level 2) dual-active-bridge
  models, and an end-to-end runner writing netlist, log, raw data, HDF5 waveforms and `summary.json`.
- `aipe_simulation.waveforms`: solver-independent waveform dataset (HDF5 with units and provenance),
  periodic steady-state identification, RMS/peak/power metrics, per-switch turn-off currents and ZVS
  conditions, volt-second balance, capacitor drift and an energy balance.

```sh
aipe-sim doctor
aipe-sim dab run --out runs/dab-level1
aipe-sim dab run --spec level2.yaml --out runs/dab-level2
python -m pytest -q tests/          # solver tests skip when ngspice is absent
```

The executed 10 kW DAB benchmark and the numerical lessons behind the models are documented in
[docs/dab-models.md](docs/dab-models.md). Manufacturer device models (Level 3) are not executed.

## Active Skills

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

## Planned Skills

_No planned skills are listed right now. Add future items to `PLANNED_SKILLS` in `scripts/update_readme.py`._

## How To Use These Skills

1. Install or copy the skill folder you want to use into your Codex skills directory.
2. Invoke a skill explicitly by name, for example: `Use $pe-ltspice-power-electronics to debug this LTspice converter simulation`.
3. Provide the engineering context the skill asks for: topology, operating range, control method, simulation tool, abnormal waveform, solver settings, and what you are trying to prove.
4. Let the skill load only the relevant `references/` files. The `SKILL.md` file gives the high-level workflow; the references contain tool-specific procedures and checklists.
5. When capturing project experience, remove customer names, project codenames, product names, exact confidential parameters, internal file paths, and any screenshot metadata that could reveal sensitive information.

## How To Add Or Update A Skill

1. Create or edit a folder named after the skill, for example `pe-new-topic/`.
2. Keep the required workflow instructions in `pe-new-topic/SKILL.md`.
3. Put detailed procedures, checklists, templates, and examples under `pe-new-topic/references/`.
4. Add `pe-new-topic/agents/openai.yaml` with a display name, short description, and default prompt.
5. Run the update and validation commands:

```bash
python3 scripts/update_readme.py
python3 scripts/validate_skills.py
```

`scripts/update_readme.py` scans all `*/SKILL.md` files and `skills.json` to regenerate this document deterministically. `scripts/validate_skills.py` checks metadata, references, UI metadata and README freshness. Update the sidecar metadata when adding a skill.

## Repository Convention

- Each skill lives in a standalone directory and must include `SKILL.md`.
- Detailed tool workflows and checklists live in `references/` and are loaded only when needed.
- UI metadata lives in `agents/openai.yaml`.
- Skill content should be primarily English so the repository can help a broader engineering audience.
- Case studies should be anonymized by default.

## Automation

GitHub Actions runs the same README freshness and skill validation checks on push and pull request. If README is stale after a skill update, the CI check fails and tells the contributor to run `python3 scripts/update_readme.py`.
