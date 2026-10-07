---
name: pe-open-fea-problem-setup
description: Select and define an open finite-element or electromagnetic solver workflow for converter thermal, magnetic, structural or high-frequency field questions. Use for physics, boundary conditions and convergence planning; this scaffold does not claim an executed multiphysics solution.
---

# Open Field-Analysis Problem Setup

Start from the physical question, observable and required fidelity. Do not select
a solver solely because it is an open alternative to a named commercial product.
This is a usable problem-definition scaffold; no solver deck or field solution
has been validated in v0.1.

Read `references/solver-selection.md` to choose physics and tool. Capture geometry
and units, constitutive data with temperature/frequency range, excitation,
boundary conditions, symmetry assumptions, contacts and desired observables.
Do not invent material loss coefficients or boundary temperatures.

Use Gmsh where appropriate for labelled regions/boundaries; a mesh alone is not
a solved physical model. Export region labels with the mesh and verify the solver
imports units and element types correctly. Test a simple analytic case before
the converter geometry, then refine mesh and relevant time/frequency resolution.

Define acceptance in terms of the engineering observable: integrated loss/flux,
hotspot/thermal resistance, displacement/stress, or S-parameters/field strength.
Check conservation and residuals plus at least three refinement levels. A small
algebraic residual does not prove discretization convergence.

Return a reproducible problem specification, solver/version selection and reasons,
data provenance, runnable commands only when verified for the installed release,
convergence plan and unresolved inputs. Mark unexecuted runs configured/not_run;
do not label synthetic assumptions as measurements. Preserve requested ANSYS or
COMSOL workflows when their specialised capability is required.
