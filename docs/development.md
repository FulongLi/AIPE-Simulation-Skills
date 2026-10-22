# Using, adding and validating skills

## How to use these skills

1. Install or copy the skill folder you want to use into your Codex skills directory.
2. Invoke a skill explicitly by name, for example: `Use $pe-ltspice-power-electronics to debug this LTspice converter simulation`.
3. Provide the engineering context the skill asks for: topology, operating range, control method, simulation tool, abnormal waveform, solver settings, and what you are trying to prove.
4. Let the skill load only the relevant `references/` files. The `SKILL.md` file gives the high-level workflow; the references contain tool-specific procedures and checklists.
5. When capturing project experience, remove customer names, project codenames, product names, exact confidential parameters, internal file paths, and any screenshot metadata that could reveal sensitive information.

## How to add or update a skill

1. Create or edit a folder named after the skill, for example `pe-new-topic/`.
2. Keep the required workflow instructions in `pe-new-topic/SKILL.md`.
3. Put detailed procedures, checklists, templates, and examples under `pe-new-topic/references/`.
4. Add `pe-new-topic/agents/openai.yaml` with a display name, short description, and default prompt.
5. Add the skill's access class, maturity, required tools, limitations and open alternative to `skills.json`.
6. Run the update and validation commands:

```bash
python scripts/update_readme.py
python scripts/validate_skills.py
```

`scripts/update_readme.py` scans all `*/SKILL.md` files, `skills.json` and the package version in
`pyproject.toml` to regenerate `README.md` deterministically. `scripts/validate_skills.py` checks metadata,
references, UI metadata and README freshness. Planned skills are listed from `PLANNED_SKILLS` in
`scripts/update_readme.py`; the section is omitted while that list is empty.

## Repository convention

- Each skill lives in a standalone directory and must include `SKILL.md`.
- Detailed tool workflows and checklists live in `references/` and are loaded only when needed.
- UI metadata lives in `agents/openai.yaml`.
- Skill content should be primarily English so the repository can help a broader engineering audience.
- Case studies should be anonymized by default.

## Tool policy

Open-source tools are the default learning path; commercial workflows remain optional professional
integrations. All eight original workflows and their reference material are retained. Five engineering
workflows added in v0.1 cover Python control analysis, ngspice switching validation, FreeCAD packaging,
KiCad power-stage review and open field-analysis problem setup. LTspice is free proprietary software.
PLECS, MATLAB/Simulink, SIMetrix/SIMPLIS, ANSYS and COMSOL require external licences for their respective
variants.

The [tool policy and capability matrix](tool-policy.md), [skill metadata](../skills.json),
[AIPE manifest](../aipe.yaml) and [Core mapping](core-mapping.md) describe exact boundaries. CAD/PCB/FEA
additions are workflow scaffolds; MCP candidates are researched only. Existing repository content has no
declared blanket licence and remains `NOASSERTION`.

## Runnable open example

Create an isolated Python environment, install `pe-python-control-analysis/requirements.txt`, and run:

```sh
python pe-python-control-analysis/scripts/buck_control.py --output buck-result.json
python -m pytest -q tests/
```

The synthetic averaged buck example checks numerical behaviour with python-control; it claims no hardware
validation. An ngspice netlist is included and exercised in Ubuntu CI; solver-dependent local tests
explicitly skip when ngspice is absent.

## Automation

GitHub Actions runs the README freshness and skill validation checks (`.github/workflows/readme-freshness.yml`)
and the package tests with ngspice installed (`.github/workflows/tests.yml`) on push and pull request. If the
README is stale after a skill or metadata update, the CI check fails and tells the contributor to run
`python scripts/update_readme.py`.
