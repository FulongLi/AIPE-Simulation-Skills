# Core v0.1 mapping

This repository has **mapped** Engineering State compatibility. It owns workflow
instructions and local artifact formats; Core owns shared state/evidence schemas.
The collection does not claim an executed full-state round trip or change a DAB
state into a buck model. The runnable report is a local analysis artifact.

| Skill input/output | Core field | Rule |
| --- | --- | --- |
| Design/operating context | project, requirements, converter, requirements.operating_points | Read topology and units before selecting a physical model |
| Actual analysis tool and version | simulation.runs[].tool; evidence[].provenance.tool | Use actual versions; do not infer successful execution from availability |
| Skill attribution | evidence[].provenance.skill | Stable skill ID and repository/revision |
| Model/netlist/geometry | simulation.runs[].model | Artifact URI, format, description and checksum where available |
| Result/log/report | simulation.runs[].outputs; evidence[].artifacts | Link actual output, never fabricated files |
| Linear buck result | evidence kind analytical; namespaced extensions if structured quantities are needed | Preserve original assumptions and reference their evidence IDs |
| Actual solver run | simulation.status, runs[].status; evidence kind simulation | Only completed after execution and result inspection; include artifacts/tool attribution |
| No installed tool / workflow scaffold | simulation.status not_run or configured | No completed run, no derived result and no physical validation claim |
| Measured data | evidence kind measurement | Only actual measurement records; synthetic examples are not measurements |

Core requires SI quantities for physical values. The local buck artifact uses
explicit units and a dimensionless loop gain; its duty-to-output plant gain is
in volts per dimensionless duty. Preserve gain definitions when mapping.
FreeCAD receives millimetres at its geometry boundary; state remains metres.
KiCad internal coordinate/API conventions must be converted at its boundary.

Evidence needs a real creation timestamp, source type/reference, activity,
input-evidence references, tool/skill attribution and review status. Record an
input assumption separately before attaching an analytical result. Do not set
validation to measured when a numerical regression passes. CAD and PCB artifacts
do not establish insulation, thermal or manufacturing acceptance.

Validate a composed state against the released/local AIPE-Core schemas and its
semantic reference validator. Schema IDs are logical v0.1 URLs; until the
release exists resolve local Core files, never silently fetch future schemas.
