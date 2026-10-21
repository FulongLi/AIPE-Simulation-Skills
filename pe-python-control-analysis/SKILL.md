---
name: pe-python-control-analysis
description: Analyse converter averaged control models, poles, frequency response and linear closed-loop response using Python and python-control. Use for model-based loop analysis; switching-device transients and hardware validation need separate workflows.
---

# Converter Averaged Control Analysis

Use Python / NumPy / SciPy / python-control as the default open path. Preserve an
explicit user choice of another tool. This skill supplies an executable ideal CCM
buck example; it is not an automatic controller designer or a switched model.

Identify topology, operating mode, operating point, loop injection definition,
modulator/sensor gains, L/C/ESR, load, switching/sampling frequencies and delays.
Ask only for missing values that change the model; record assumed values as such.
Never apply a buck transfer function to boost, resonant or isolated converters.

For an ideal CCM buck, use `Gvd(s) = Vin / (LC s^2 + (L/R)s + 1)`. Check its
DC gain, poles and dimensions before adding feedback. Distinguish duty perturbation
from voltage reference and include the actual sensor/PWM gains. Read
`references/model-boundaries.md` when selecting fidelity or interpreting margins.

Run the included example from this skill's folder after installing
`requirements.txt` in an isolated Python environment:

```sh
python scripts/buck_control.py --output buck-result.json
```

The output describes a synthetic 48 V ideal plant and a deliberately simple
proportional loop. Report steady-state error; do not imply integral action or
claimed engineering acceptance. For a real design, replace its inputs/model and
evaluate input/load/tolerance corners, crossover versus sampling/switching
frequency, delay, saturation and perturbation amplitude. Compare a switched model
or measurements before treating the compensation as validated.

For the isolated dual active bridge under single-phase-shift control the repository
package `aipe_simulation.control` provides a worked digital baseline: a cycle-averaged
plant with stated assumptions, PI and 2P2Z (DF22) compensators, z-plane crossover and
phase-margin evaluation with sampling, computation and measurement delays, and a
closed-loop host simulation; its specification is `docs/dab-sps-control-spec.md` at
the repository root. It uses NumPy only, is verified against the ngspice switching
model for steady-state power, and does not replace switched-model transient or
hardware validation of the control loops.

Return model equations, assumptions, tool versions, SI inputs, output artifact,
and failed/unchecked criteria. Map evidence to Core using `docs/core-mapping.md`
from the repository when available; a JSON report alone is not an Engineering
State. No measured performance is produced by this skill.
