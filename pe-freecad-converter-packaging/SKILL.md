---
name: pe-freecad-converter-packaging
description: Plan and model converter mechanical packaging in FreeCAD using explicit envelope dimensions, mounting and keepout constraints, interference checks and reproducible exports. Use for CAD packaging; electrical clearance certification and thermal solver validation are outside this skill.
---

# Converter Mechanical Packaging with FreeCAD

Use native FreeCAD Python/API or macros first. A generic FreeCAD MCP supplies
operations; this skill supplies the engineering checks. No MCP is required or
installed by this skill. Keep explicitly requested commercial CAD workflows.

Capture board, heatsink, connector and magnetic-component envelopes; mounting
datums; airflow direction; service/tool access; and assembly tolerances. Identify
which dimensions are measured, datasheet-derived or placeholder assumptions.
Use SI lengths in exchange data and convert explicitly to millimetres at the
FreeCAD geometry boundary. Avoid guessed creepage/clearance requirements.

Create named parametric solids and keepout bodies in a scratch document. Check
positive dimensions, wall thickness, mounting alignment, overlapping volumes and
access after each relevant recompute. Export both editable FCStd and STEP with
an input dimension table and tool/version attribution. Re-import an export to
inspect scale and missing geometry before release.

Read `references/interfaces.md` when choosing native/API/MCP execution. If
FreeCAD is unavailable, deliver the constraint table, modelling script proposal
and validation plan marked **not executed**; do not claim fabricated CAD files.

Record unresolved material properties and thermal interfaces separately.
Packaging fit does not prove electrical insulation compliance, manufacturability
or thermal performance. Export evidence can map into Core artifact references;
the detailed geometry stays in FreeCAD.
