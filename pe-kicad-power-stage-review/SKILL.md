---
name: pe-kicad-power-stage-review
description: Review or develop a converter power-stage PCB in KiCad with explicit current paths, gate-loop placement, creepage constraints and ERC/DRC evidence. Use for power-stage layout reasoning and reproducible checks; DRC alone does not certify safety or EMI performance.
---

# Power-Stage PCB Review with KiCad

Use KiCad CLI for repeatable checking/export and the GUI or supported IPC API
for board edits. Preserve user-approved placement and requirements. Generic MCP
operations do not replace the power-stage review described here.

Collect schematic/board, stackup, copper weight, voltage/current waveforms,
switching edge rates, assembly limits and the applicable insulation requirements.
Record unknowns; do not invent safety clearances from bus voltage alone.

Trace commutation and gate-drive loops, local decoupling, Kelvin returns,
high-dv/dt nodes, sensing returns and thermal paths. Inspect placement before
routing. Check copper bottlenecks, via sharing, connector ratings, keepouts and
the physical separation of noisy and sensitive circuits. State which checks
need field extraction, thermal analysis or prototype measurements.

Read `references/cli-and-ipc.md` before scripted operation. Save board copies,
run ERC and DRC with exit-on-violations and inspect reports. Track intentional
exceptions with engineering rationale; do not silently suppress findings. Check
net connectivity and reviewed changes again after routing or zone refill.

Return annotated findings, actual command/version, reports and unresolved checks.
Fabrication exports require an explicit project deliverable; packaging generated
Gerbers does not certify the board. If KiCad is unavailable, mark the review as
document-only and leave execution evidence unset.
