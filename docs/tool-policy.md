# Tool policy and capability matrix

AIPE is open-source first, commercial compatible. Choose the actual engineering
capability and physical assumptions before choosing a tool. Repository-level
proprietary tools are optional; a skill variant explicitly targeting one of
them still requires that tool and its external licence. `skills.json` records
these per-skill requirements. The eight original workflows are retained.

| Engineering capability | Preferred open path | Optional tool/variant | Interface | AIPE skill | v0.1 evidence |
| --- | --- | --- | --- | --- | --- |
| Averaged control analysis | Python, NumPy, SciPy, python-control; SymPy for symbolic derivation | MATLAB/Simulink; existing PLECS/LTspice loop diagnosis | Python; proprietary tool APIs | pe-python-control-analysis / pe-control-loop-debug | Runnable numerical example and invariants |
| Switched circuits | ngspice; assess eSim/GeckoCIRCUITS by required model | LTspice (free proprietary), PLECS, SIMetrix/SIMPLIS | Batch netlists; tool-specific scripting | pe-ngspice-switching-validation plus retained variants | Synthetic netlist; Ubuntu CI smoke test |
| Converter packaging | FreeCAD | User-selected commercial CAD | Python/CLI; evaluated MCP | pe-freecad-converter-packaging | Constraint/verification scaffold; CAD not executed |
| Power-stage PCB review | KiCad | Vendor-specific EDA if requested | CLI, versioned IPC; evaluated MCP | pe-kicad-power-stage-review | Engineering review scaffold; KiCad not executed |
| Low-frequency magnetic/thermal field setup | Gmsh + Elmer or GetDP where appropriate | ANSYS / COMSOL | CLI, mesh/solver input files | pe-open-fea-problem-setup and retained field skills | Problem-definition scaffold; no FEA execution |
| Structural / thermal field setup | CalculiX where suitable | ANSYS / COMSOL | CLI / `.inp` | pe-open-fea-problem-setup | Solver selection only |
| High-frequency EM | openEMS | Commercial field solvers | Python/Octave | pe-open-fea-problem-setup | Solver selection only |
| Numerical experimentation/documentation | Python/SciPy, SymPy, Jupyter; GNU Octave when compatible | MATLAB | Python/CLI/notebooks | pe-python-control-analysis | Python example executed; other runtimes researched |
| Digital control / FPGA bring-up | Open numerical timing/model checks; target-specific toolchain if available | Vendor compiler/FPGA suites, hardware/debug probes | Target-specific | pe-dsp-fpga-control-debug | Existing workflow retained; no universal open hardware path claimed |

No solver is a perfect replacement for every commercial capability. Device model
dialects, event handling, code generation, material libraries, meshing and
specialised loss formulations can be tool-specific. Reduced-fidelity open paths
must state what they exclude. FEMM is source-available under Aladdin with
redistribution restrictions; do not label it OSI-open simply because it is free.

The independent [external tool catalogue](https://github.com/FulongLi/awesome-open-source-power-electronics)
contains the 2026-10-07 source/link/activity audit. AIPE-Registry indexes this
collection's capability manifest, not every external project. GSEIM historical
links were unavailable during review, so it is retained in the catalogue without
selecting it as a default executable dependency. OpenModelica is worth assessing
for system models, but v0.1 does not ship a validated Modelica workflow.

## MCP decision

FreeCAD's neka-nat/freecad-mcp and KiCad's mixelpixx/KiCAD-MCP-Server are
**evaluated**, never implicitly installed or marked supported. Their per-skill
references document observed commits, licence, platform/version claims, execution
privileges and direct API/CLI alternatives. Native scripting is sufficient for
the v0.1 examples and avoids a connector dependency. Connector suitability must
be rechecked at the exact selected revision before adoption.

## Commercial and free proprietary variants

LTspice is [free to use from Analog Devices](https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html),
but not open-source. PLECS, MATLAB/Simulink, ANSYS, COMSOL and SIMetrix/SIMPLIS are
commercial integrations requiring external licences; trials or limited editions
do not make them mandatory/free ecosystem dependencies. Vendor tool and model
licences remain separate from this repository's content rights.

Reviewed 2026-10-07 using upstream product/interface sources. Availability or
licence classification is not a claim that AIPE tested every supported version.
