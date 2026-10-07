# v0.1 validation record

Reviewed 2026-10-07. The 13 skill folders validate, including all eight retained
workflows and five additions. New skill metadata and instructions were checked
with the skill-creator validator. README generation is deterministic and contains
no wall-clock date. JSON/YAML/Markdown/code use LF checkout rules.

Local Python 3.10.11, python-control 0.10.2, NumPy 2.2.6 and SciPy 1.15.3:

```sh
python scripts/update_readme.py
python scripts/validate_skills.py
python pe-python-control-analysis/scripts/buck_control.py --output buck-result.json
python -m unittest discover -s tests -v
```

Five local tests passed; one ngspice test skipped because the solver was absent.
Numerical checks cover DC gain and final value across 3 input voltages and 3
loads, stable linear poles, rejection of nonphysical/nonfinite inputs, metadata
consistency, retained LTspice classification and deterministic generation.

Ubuntu CI installs ngspice and runs the switched buck at 100 ns and 50 ns maximum
time steps, checking mean output and sensitivity over the same late window.
The workflow is configured here; its actual run status is recorded by GitHub
checks on the PR. A local skip is not a completed solver run.

The manifest is validated against the coordinator's AIPE-Registry v0.1 schema
during cross-repository validation. Compatibility is mapped: no complete state
adapter, installed CAD/FEA run, MCP execution, commercial-tool run, measurement
or physical device validation is claimed. Scaffolds provide engineering input,
execution and verification requirements without fabricated output artifacts.
