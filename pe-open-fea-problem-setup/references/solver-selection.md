# Solver selection by physics

Reviewed 2026-10-07; upstream documents describe capability, not AIPE validation.

| Question | Candidate and interface | Boundary |
| --- | --- | --- |
| Low-frequency magnetic/electrothermal fields | [Elmer FEM](https://github.com/ElmerCSC/elmerfem), ElmerSolver SIF/CLI; [GetDP](https://getdp.info/), CLI and `.pro` formulation | Material laws and coupled loss/heat sources require evidence; Elmer has GPL/LGPL component terms |
| Mesh generation and region labelling | [Gmsh](https://gmsh.info/), CLI/Python/C++ | GPL-2.0-or-later; no standalone thermal or EM answer from a mesh |
| Structural stress and thermal fields | [CalculiX](https://www.calculix.de/), `ccx` and `.inp` | GPL-2.0-or-later; structural/thermal emphasis, not a general EM solver |
| High-frequency EM / propagation | [openEMS](https://www.openems.de/), Python/Octave FDTD | GPL-3.0; resolve smallest mesh cell and relevant wavelength; not a direct quasi-static core-loss replacement |
| 2D/axisymmetric magnetics | [FEMM](https://femm.info/doku/doku.php?id=Download), Lua/pyFEMM/Octave | Aladdin source-available licence restricts redistribution; native Windows; keep outside strict OSI-open default |

For thermal conduction first verify a slab against `Rth = length/(k area)`;
state uniform material, 1D heat flow and boundary assumptions. Convection/contact
uncertainty may dominate mesh error. For magnetics verify a simple reluctance
case before nonlinear/hysteretic models, then check flux continuity and energy.
For stress verify support constraints avoid unintended rigid-body modes.

Record platform/compiler/build and installed solver version; distribution
availability differs. Do not treat proprietary material databases, remote solver
services or vendor meshes as automatically redistributable because a solver is
open. ANSYS/COMSOL remain optional professional paths with external licences;
feature parity is neither implied nor required.
