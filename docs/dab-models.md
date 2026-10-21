# Executed DAB switching models (`aipe_simulation.dab`)

This document describes the dual-active-bridge circuit models that the
`aipe_simulation` package generates for ngspice, the conventions they share, the
numerical lessons that shaped them, and the executed benchmark results of
2026-10-21 (ngspice 47, Windows 11, workspace `runs/`). Every number below comes
from an executed solver run whose netlist, log, raw data, HDF5 dataset and
summary are stored with SHA-256 hashes; nothing is inferred from a plot.

## Conventions (shared by generator, analysis and the Design-Agent model)

| Item | Convention |
| --- | --- |
| Ports | port 1 = primary DC bus `p_pos`/0; port 2 = secondary DC port `s_pos`/0 (both negatives on the SPICE ground; the E/F ideal transformer has no galvanic path) |
| Bridge nodes | legs A (S1 high, S2 low, node `a`), B (S3, S4, node `b`), C (S5, S6, `c`), D (S7, S8, `d`); `v_ab = v(a) - v(b)`, `v_cd = v(c) - v(d)` |
| Turns ratio | `n = N_p / N_s`; primary-referred secondary voltage `n v_cd` |
| Series current | `i_L` from node `a` through the external inductance towards the transformer; `i_s` out of the secondary winding into node `c`; `i_p_ideal = i_s / n` |
| Phase shift | `phi > 0`: secondary lags, power flows port 1 to port 2; `t_phi = phi T / 2 pi` |
| Time origin | centre of the primary positive half-cycle (S1, S4 on); magnetising current zero crossing is at `t_phi` |
| Switch current | positive = drain-to-source conduction |
| DC currents | `i_dc1 = -i(V1)` into the converter; `i_dc2 = i(V2)` into port 2 (for the RC port, `V2` is a 0 V sense source in series with the load) |

## Level 1 — ideal switching model

Ideal `SW` switches (R_on 1 mOhm, hysteretic transition, 10 ns gate edges whose
mid-points fall on the ideal switching instants), antiparallel ideal diodes
(conduct only in the zero-dead-time edge overlap), ideal E/F transformer with an
explicit magnetising inductance (1 mH assumption), external series inductance
35 uH, 20 mOhm series resistance (physical winding resistance that also damps
start-up offsets), stiff DC sources at both ports, zero dead time.

Nominal benchmark (800 V -> 400 V, 100 kHz, n = 2, phi = 22.5 deg, analytic
initial conditions, 24 cycles, t_max = T/400):

| Quantity | Analytic (lossless SPS) | ngspice Level 1 | Relative error |
| --- | --- | --- | --- |
| Output power | 10 000.0 W | 9 996.8 W | 3.2e-4 (the 5.1 W difference is the modelled resistive loss) |
| Port 1 DC current | 12.500 A | 12.503 A | 2.0e-4 |
| Port 2 DC current | 25.000 A | 24.992 A | 3.2e-4 |
| i_L RMS | 13.6775 A | 13.6779 A | 3e-5 |
| i_L peak | 14.286 A | 14.315 A | 2.1e-3 (magnetising current adds to the external inductor current) |
| Measured phase shift | 22.5 deg | 22.5000 deg | — |
| Per-switch turn-off current, primary / secondary | 14.29 / 28.57 A | 14.26 / 32.5 A (secondary includes magnetising current) | — |

Periodicity error 1.8e-6, half-wave antisymmetry error 3.8e-4, volt-second
imbalance 5e-3 relative, all eight switches satisfy the ZVS current condition,
unaccounted power -0.5 W of 10 kW. A zero-initial-condition run (r_series_p
raised to 0.2 Ohm) settles to the same steady state after 34 cycles. Time-step
convergence (T/100 ... T/1600): output power changes 8e-6 between T/400 and
T/1600, i_L RMS 6e-5, turn-off currents < 1e-8.

## Level 2 — behavioural non-ideal model

Adds: behavioural channel (B-source conductance with a C1-continuous clamped
smoothstep of the gate voltage: exactly off below `Vt - w`, exactly on above
`Vt + w`), on-resistance at the design junction temperature, 200 ns dead time
(TIDUES0), linear energy-equivalent Coss with a 1 Ohm series damping resistor,
SiC body-diode single-point fit (N = 4, Rs = 0.117 Ohm from VSD 5.5 V at 20 A,
C3M0040120K), transformer leakage split from the external inductance, winding
resistances, DC-link film capacitor with ESR/ESL and local ceramic decoupling
(TIDUES0 BOM), source impedance, RC output port (60 uF, 16 Ohm). All values are
datasheet-sourced or labelled assumptions in
`AIPE-Workflows/examples/dab-10kw/level2-circuit-spec.yaml`.

Executed result (160 cycles, t_max = T/400, 1.4e5 time points): total loss about
136 W of 9.7 kW drawn, of which about 123 W is dissipated in the eight switch
pairs (conduction at 58.7 mOhm for all devices, which overstates the secondary
bridge, plus body-diode conduction during dead time and Coss damping); peak
drain-source voltages 810 V (primary) and 412 V (secondary); every switch turns
on with a negative drain-source voltage (body diode conducting), i.e. true ZVS
under the behavioural model; the open-loop RC port settles near 392 V because
the losses reduce the transferred power at fixed phase shift (closed-loop
control restores 400 V, see the control specification).

## Level 3 — manufacturer models

Not executed. Manufacturer LTspice/PLECS models exist for the shortlisted
devices (see the device shortlist in AIPE-Workflows) but their licences restrict
redistribution and their ngspice compatibility must be diagnosed per model; the
generator reserves `level: 3` for qualified adaptations with validation against
manufacturer reference conditions.

## Numerical lessons (all confirmed by failing runs)

1. Always skip the DC operating point (`uic`): with static gate states it shorts the inductors and the ideal transformer through milliohm paths.
2. A capacitance directly across a milliohm switch (diode `Cjo` or linear Coss) is unsolvable; Coss needs a series damping resistor and `Cjo` stays zero.
3. Never emit placeholder parasitics (1 pH in series with 5 mOhm); omit zero-valued elements.
4. ESL against Coss resonates near 100 MHz with Q in the thousands; a parallel `sqrt(L/C)` damping resistance across each parasitic inductor is required and is reported as an assumption.
5. DC-link capacitors must start at the bus voltage under `uic`; nanosecond commutation edges through a 20 nH bulk-capacitor ESL produce hundreds of volts of overshoot unless local low-inductance decoupling is modelled, as in real designs.
6. The hysteretic `SW` element fails to converge once R_on is tens of milliohms and Coss branches hang on the node; the behavioural smoothstep channel converges. A tanh channel is wrong: its tail leaves an off-conductance of `G_on * 1e-4` (kilowatts of fictitious loss).
7. The magnetising current's periodic initial value at the primary centre is `-V2' t_phi / L_m`; otherwise a DC offset decays with `L_m / R` (tens of ms).
8. The energy balance must count the capacitors' stored-energy drift and the true switch dissipation `avg(v_ds i)`; `i_rms^2 R_on` is only an estimate.
9. Newton fragility at off-nominal operating points (d != 1) is removed by physically benign settings: 20 ns gate edges, `abstol` 1e-8 A / `vntol` 1e-5 V, or a 3 Ohm Coss damping resistor; a robustness study at n = 2.1 showed all of them converging to the same physics (output power within 0.05 %, losses within 3 W).

## Artefacts and reproduction

```sh
pip install -e ../AIPE-Simulation-Skills
set AIPE_TOOLS_DIR=<workspace>/tools        # or put ngspice_con on PATH / set AIPE_NGSPICE
aipe-sim doctor
aipe-sim dab run --out runs/dab-l1 --cycles 24
aipe-sim dab run --spec ../AIPE-Workflows/examples/dab-10kw/level2-circuit-spec.yaml --out runs/dab-l2
aipe-sim dab analyse --run runs/dab-l2
```

Each run directory contains `spec.json`, `metadata.json`, `circuit.cir`,
`circuit.log`, `circuit.raw`, `waveforms.h5` (HDF5, `/time` and
`/channels/<name>` with units), `summary.json` and `run.json` with command,
versions, hashes and status.
