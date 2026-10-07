#!/usr/bin/env python3
"""Generate README.md from skill metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

PLANNED_SKILLS: list[dict[str, str]] = []


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"Missing frontmatter: {path}")

    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.parent.name


def skill_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    policy = {s['id']: s for s in json.loads((ROOT / 'skills.json').read_text())['skills']}
    for skill_md in sorted(ROOT.glob("*/SKILL.md")):
        if skill_md.parts[-2].startswith("."):
            continue
        meta = parse_frontmatter(skill_md)
        references = sorted((skill_md.parent / "references").glob("*.md"))
        agents = skill_md.parent / "agents" / "openai.yaml"
        rows.append(
            {
                "folder": skill_md.parent.name,
                "name": meta.get("name", skill_md.parent.name),
                "title": first_heading(skill_md),
                "description": meta.get("description", ""),
                "references": str(len(references)),
                "status": policy[skill_md.parent.name]['maturity'] if agents.exists() else "draft",
                "access": policy[skill_md.parent.name]['access'],
            }
        )
    return rows


def generate() -> str:
    rows = skill_rows()

    active_table = "\n".join(
        [
            "| Skill | Maturity | Access | Focus | References |",
            "| --- | --- | --- | --- | ---: |",
            *[
                f"| [`{row['name']}`](./{row['folder']}/SKILL.md) | {row['status']} | {row['access']} | {row['title']} | {row['references']} |"
                for row in rows
            ],
        ]
    )

    if PLANNED_SKILLS:
        planned_table = "\n".join(
            [
                "| Planned Skill | Status | Focus |",
                "| --- | --- | --- |",
                *[
                    f"| `{item['name']}` | {item['status']} | {item['focus']} |"
                    for item in PLANNED_SKILLS
                ],
            ]
        )
    else:
        planned_table = "_No planned skills are listed right now. Add future items to `PLANNED_SKILLS` in `scripts/update_readme.py`._"

    return f"""# AIPE Simulation Skills

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

## Active Skills

{active_table}

## Planned Skills

{planned_table}

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
"""


def main() -> None:
    README.write_text(generate(), encoding="utf-8")


if __name__ == "__main__":
    main()
