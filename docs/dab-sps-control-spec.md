# AIPE 10 kW DAB: digital single-phase-shift control specification (baseline)

Status: host-side baseline, verifiable by `python -m pytest -q tests/test_control_*.py` and reproducible with
`aipe-sim control design`, `aipe-sim control simulate --out DIR` and `aipe-sim control verify --out DIR`
(package `aipe_simulation.control`, this repository). No firmware was built or executed on a controller
target; see section 10. Every number below is either an AIPE assumption (marked), a value computed by the
package from those assumptions (reproducible from the stated command), or a TI published figure (marked
"TI", source: `AIPE-Workflows/examples/dab-10kw/references/tida-010054-fact-sheet.md`, which cites the
TIDA-010054 design guide TIDUES0). TI's reference design operates at 800 V to 500 V with n = 1.6; the AIPE
benchmark operates at 800 V to 400 V with n = 2, so TI's controller values are quoted as a reference
implementation and are not reused.

## 1. Scope and plant

| Item | Value | Basis |
| --- | --- | --- |
| Topology, modulation | single-phase DAB, single-phase-shift (SPS); EPS/DPS/TPS are future work | AIPE task |
| V1 / V2 / P | 800 V / 400 V / 10 kW, bidirectional | AIPE specification |
| f_sw, n = N_p/N_s, L (primary referred) | 100 kHz, 2, 35 uH | AIPE specification |
| Nominal phase shift | 22.5 deg = 0.3927 rad gives exactly 10 kW (P = V1 n V2 phi (pi - abs(phi)) / (2 pi^2 f_sw L)) | computed |
| P_max (abs(phi) = 90 deg) | 22 857 W | computed (TI quotes 22.85 kW for its 800 V x 1.6 x 500 V design, the same V1 V2' product) |
| Output capacitance C2 | 400 uF | AIPE assumption for the control design; TI uses 60 uF film plus ceramics for its own loop |
| Dead time | 200 ns | TI value (TIDUES0 Eq. 22); adopted by the AIPE Level 2 circuit model |
| Sign convention | phi > 0: secondary bridge lags, power flows port 1 -> port 2; i_L from node a towards the transformer | `aipe_simulation.dab` |

Cycle-averaged plant used for the control design (`control/plant.py`, assumptions stated in
`MODEL_ASSUMPTIONS`): lossless SPS law, ideal transformer, no magnetising current, stiff port 1 (optional
static source resistance), port-2 capacitor with resistive and/or current-source load, exact ZOH
discretisation per switching period. Because I2 = n V1 phi (pi - abs(phi)) / (2 pi^2 f_sw L) does not depend
on V2, the SPS-controlled DAB is a phase-shift-controlled current source into C2.

Small-signal gains at the nominal point (computed): dI2/dphi = 54.57 A/rad (0.952 A/deg), range 36.4 A/rad
(phi = 45 deg) to 72.8 A/rad (phi -> 0); dP/dphi = 21.83 kW/rad (381 W/deg); output-port pole
1/(2 pi R C2) = 24.9 Hz at full load (R = 16 Ohm).

## 2. Sampling, ISR and delays

| Item | Specification | Basis |
| --- | --- | --- |
| Control ISR rate | f_s = f_sw = 100 kHz, T_s = 10 us, one ISR per switching period, both loops every ISR | AIPE choice (TI runs its control ISR from EPWM1 as well; the ISR rate is not published) |
| Voltage sample | v2 sampled at the primary counter zero (period boundary); ripple at 2 f_sw is filtered by C2 | AIPE |
| Current sample | i2 (port-2 DC current) shall represent the average over the previous switching period (sinc filter or oversampled ADC window of one period); this is modelled as one sample of measurement delay | AIPE requirement (TI measures the secondary DC current through an SDFM delta-sigma path) |
| Computation delay | the phase register computed in period k is shadow-loaded at the boundary k+1: one sample delay (modelled as z^-1); the option `computation_delay_samples = 0` quantifies the idealised case | AIPE |
| Loop delays | current loop: 2 samples (computation + measurement) = 14.4 deg at 2 kHz; voltage loop sees the inner closed loop plus the ZOH capacitor model | computed |
| ADC trigger / ISR source | ADC SOC and ISR triggered from the primary ePWM module every period | AIPE; TI triggers its SOC from EPWM1 and ISR1 on the EPWM1 TBCTR_U_CMPC event |

ISR timing budget (AIPE allocation at 120 MHz CPU clock, TI's F280039C class device; 1200 cycles per period;
these are targets to be verified by profiling, not measurements):

| Block | Allocated cycles |
| --- | ---: |
| ISR entry, context, acknowledge | 40 |
| ADC/SDFM result read, offset/scale to SI (v2, i2, i1, v1, transformer current flags) | 60 |
| Protection comparisons, latch and trip handling | 40 |
| Voltage loop DF22 (2P2Z) with clamp | 40 |
| Current loop PI with clamping and tracking anti-windup | 40 |
| Modulator: command limit, slew limit, split into coarse counts + fine steps, write phase registers | 80 |
| Supervisory state machine (soft start, hand-over, shutdown, reset) | 60 |
| Decimated logging / telemetry | 100 |
| ISR exit | 40 |
| Total | 500 (4.2 us, 42 % of the period) |

The budget leaves more than half the period for the SDFM/communication interrupts and guarantees that the
register update is ready before the next period boundary, which is the assumption behind the one-sample
computation delay in the loop analysis.

## 3. PWM configuration

Reference implementation (TI, TIDUES0 sections 4.1.2.3-4.1.2.4): ePWM1/2 drive the primary legs and ePWM3/4
the secondary legs on GPIO0-7; up-down count with TBPRD = 500 at 100 kHz; leg-to-leg 180 degrees by swapping
the xA/xB outputs; the secondary phase shift is set through a high-resolution phase register; the lead/lag
direction is selected by the sync count direction (`DAB_phaseSyncPrimToSecCountDirection`); 200 ns
high-resolution dead band; measured phase steps of 499.8/501.6 ns for 500/502 ns set-points; software
phase-shift limit 0.13 pu. TI does not publish the ePWM clock behind TBPRD = 500.

AIPE modulator model (`control/sps_modulator.py`, defaults; the clock and fine step are AIPE assumptions
consistent with TBPRD = 500):

| Item | Specification |
| --- | --- |
| Time base | 100 MHz counter clock, up-down count, TBPRD = 500 -> 10 us period; coarse step 10 ns |
| Eight outputs | module A: S1 (high) / S2 (low); module B: S3 / S4 with swapped outputs so that S4 = S1 and S3 = S2 pattern (leg-to-leg 180 deg); modules C and D likewise for S5-S8 |
| 50 % duty | compare at TBPRD/2 with set-on-up / clear-on-down: the S1/S4 pulse is centred on the counter peak, which is the time origin t = 0 of `aipe_simulation.dab.gating` |
| Dead band | 20 counts = 200 ns per leg transition. Model modes: `centred` (ideal instant at the centre of the dead band, identical to `SpsTiming`) and `delayed_turn_on` (rising-edge/falling-edge delay of a PWM dead-band submodule); the two differ by a 100 ns shift of the whole pattern and give the same phase shift |
| Phase register | realisable phase-shift time = direction x (coarse counts x 10 ns + fine steps x 150 ps); the register of period k is loaded at the period boundary from the value computed in period k-1 |
| Direction | sign of the command: +1 secondary lags (power 1 -> 2), -1 secondary leads (power 2 -> 1); zero shift = 0 |
| Resolution | coarse 10 ns = 0.36 deg = 137 W (1.4 % of 10 kW) at the nominal point; fine 150 ps = 0.0054 deg = 2.1 W (0.02 %). A high-resolution phase register is therefore required for a smooth 2 kHz current loop; the coarse grid alone would produce a 137 W limit cycle |
| Command limit | abs(phi) <= 45 deg (t_phi <= 1.25 us): keeps the per-period gate pattern well ordered and the operating point on the monotonic side of the SPS law |
| Slew limit | 1 deg per period (27.8 ns, 100 deg/ms): bounds the transient DC offset of the series current to about 0.6 A per update; soft start uses a separate 2 deg/ms ramp |
| Verification | edge times of all eight gates equal `SpsTiming` to 1e-20 s in exact mode for phi in {0, +-10, +-22.5, +-35, +-45, 60} deg; in quantised mode the secondary edges are within one fine step; 22.5 deg (625 ns) is realised as 62 coarse counts + 33 fine steps (624.95 ns) |

## 4. Controller coefficients and derivation

Design targets (AIPE): current loop crossover 2 kHz, voltage loop crossover 300 Hz with 60 deg phase margin,
inner/outer separation about 7, high-frequency 2P2Z pole at 5 kHz (f_s/20). Justification against the
100 kHz switching frequency: the cycle-averaged plant ignores the intra-period series-current dynamics,
which is acceptable when the loop crossover is far below f_sw (here f_sw/f_c,i = 50); the two samples of
delay cost 14.4 deg at 2 kHz, leaving a first-order-like current loop with more than 90 deg of phase margin;
the voltage loop at 300 Hz is slow enough for the inner loop to look like a unity gain with 8.5 deg of lag.
Justification against the assumed C2 = 400 uF: abs(Z_C2(300 Hz)) = 1.33 Ohm, so a 36 A load change (full
forward load to 12.5 A regenerative and back) produces about 29 V (7.6 %) of deviation and a 19 A step about
15 V (3.7 %); a smaller capacitor or tighter transient limits would require a higher crossover.

### 4.1 Current loop (PI on the port-2 DC current)

Plant: static gain K_i = dI2/dphi = 54.567 A/rad at the nominal point, with z^-1 (computation) and z^-1
(measurement). Controller structure: u[k] = Kp e[k] + x[k], x[k] = x[k-1] + Ki T_s e[k] (backward Euler),
output clamped to +-45 deg, clamping anti-windup plus tracking anti-windup fed with the modulator's
limited (pre-quantisation) phase shift of the previous update.

Derivation: Kp is set from the admissible high-frequency loop gain K_i Kp = 0.25 (about 12 dB before the
integral term adds its share at Nyquist); Ki solves abs(K_i (Kp + Ki T_s / (1 - z^-1))) = 1 at
z = exp(j 2 pi 2000 T_s) (closed form, quadratic in Ki T_s).

| Coefficient | Value |
| --- | --- |
| Kp | 4.5815e-3 rad/A |
| Ki | 219.25 rad/(A s); per sample Ki T_s = 2.1925e-3 rad/A |
| Output limit | +-0.7854 rad (+-45 deg) |

Margins on the z-plane (computed by `stability_margins`, 6000-point log grid up to Nyquist):

| Operating point | Crossover | Phase margin | Gain margin |
| --- | ---: | ---: | ---: |
| nominal (K_i = 54.57 A/rad) | 2000 Hz | 93.6 deg | 10.0 dB at 23.3 kHz |
| phi -> 0 (K_i = 72.76 A/rad) | 2781 Hz | 94.4 deg | 7.5 dB |
| phi = 45 deg (K_i = 36.38 A/rad) | 1297 Hz | 92.6 deg | 13.5 dB |

### 4.2 Voltage loop (2P2Z, DF22)

Rest of the loop: inner closed loop T_i(z) = K_i z^-1 C_PI / (1 + K_i z^-2 C_PI) times the exact ZOH
capacitor model Z(z) = R (1 - a) / (z - a), a = exp(-T_s / (R C2)) = 0.99844 at R = 16 Ohm. Its phase at
300 Hz is -93.65 deg. Continuous prototype C(s) = K (1 + s/w_z)^2 / (s (1 + s/w_p)): the coincident zeros are
placed from the phase-margin target, 2 atan(f_c/f_z) = 60 - 180 + 93.65 + 90 + atan(300/5000) =
67.08 deg, giving f_z = 452.5 Hz; the pole is 5 kHz; Tustin discretisation pre-warped at 300 Hz
(`tustin_2p2z`) and K = 1006.4 A/(V s) scaled for unity loop gain at 300 Hz.

DF22 difference equation (TI DCL convention) y[n] = b0 e[n] + b1 e[n-1] + b2 e[n-2] - a1 y[n-1] - a2 y[n-2],
e in volts, y = current reference in amperes, clamped to +-30 A with the clamped value written back into
the output history:

| Coefficient | Value |
| --- | --- |
| b0 | 3.4765100 |
| b1 | -6.7580839 |
| b2 | 3.2843065 |
| a1 | -1.7284826 |
| a2 | 0.7284826 (1 + a1 + a2 = 0: integrator) |
| zeros / poles (z) | 0.97196 (double) / 1.0, 0.72848 |

| Operating point | Crossover | Phase margin | Gain margin |
| --- | ---: | ---: | ---: |
| full load (16 Ohm), inner loop nominal | 300.0 Hz | 60.0 deg | 28.4 dB at 18.1 kHz |
| no resistive load (pure C2) | 300.7 Hz | 55.4 deg | 28.4 dB |
| full load, inner loop at maximum plant gain | 301.2 Hz | 62.4 deg | 25.0 dB |

The linear closed-loop reference step has 23 % overshoot; the set-point is therefore rate-limited to
20 V/ms in the supervisory layer. Consistency check: a 2 V set-point step in the host simulation (quantiser
off) follows the linear z-domain prediction within 8 % of the step (`test_small_signal_response_matches_linear_discrete_model`).

TI reference values (TI, TIDUES0 pp. 61, 68, for TI's own per-unit scaling and operating point; quoted for
comparison only, not used): voltage loop DF22 A1 = -1.8756666, A2 = 0.8756666, B0 = 1.4329852,
B1 = -2.7994568, B2 = 1.3664965; current loop PI Kp = 0.5, Ki = 0.0063030, output +-0.13 pu. TI publishes
no numeric bandwidth or phase margin (SFRA plots only).

## 5. Protection thresholds (AIPE assumptions)

| Protection | Threshold | Action | Note |
| --- | --- | --- | --- |
| Transformer primary current peak | 40 A (2.8 x the 14.3 A nominal peak; worst normal case incl. current-limited start at d = 0.875 is about 23 A; secondary 80 A informational) | hardware comparator trips all gates within the period, latched | TI uses 45 A primary / 70 A secondary Hall-sensor trips through a GPIO trip. The host model emulates the trip with the quasi-static lossless peak of the previous period (one period of latency) |
| Port-2 over-voltage | 460 V (1.15 x 400 V) | trip, latched | |
| Port-2 under-voltage | 300 V, armed in RUN only | trip, latched | not armed during soft start |
| Soft-start timeout | 50 ms without hand-over | trip, latched | |
| Current reference clamp | +-30 A (1.2 x nominal), i.e. phi = 27.97 deg at d = 1 | voltage loop output limit | enforces current limiting; overload at 12 Ohm settles at 361.7 V (simulated) |
| Phase-shift limit / slew | +-45 deg / 1 deg per period | modulator | TI: software limit 0.13 pu |
| Precharge interlock | start accepted only if v2 >= 0.8 V_ref (320 V) | start rejected otherwise | the cycle-averaged model cannot represent start-up from 0 V (diode-rectifier/precharge mode is future work) |
| Fault reset | explicit command, accepted only when no condition persists; gates stay off until a new start | | |

## 6. Start-up and shutdown sequences

State machine IDLE/OFF -> SOFT_START -> RUN -> SHUTDOWN -> OFF, FAULT from any active state (latched).

1. Start: precharge interlock (v2 >= 320 V), gates enabled with phi = 0.
2. Soft start: open-loop phase-shift ramp at 2 deg/ms up to 30 deg maximum, protection active, UV not armed.
3. Hand-over when v2 >= 0.99 V_ref (or the ramp limit is reached): the PI integrator is initialised to the
   applied phase shift and the DF22 history to the measured current (bumpless).
4. RUN: closed loops, set-point rate limit 20 V/ms.
5. Shutdown: voltage loop disengaged, phase shift ramped to zero at 2 deg/ms, then all gates off (OFF).

Simulated (nominal scenario, 25 % load at start, `summary.json` of `aipe-sim control simulate`): hand-over
at 6.82 ms with v2 = 396.0 V and phi = 13.6 deg; v2 minimum during the ramp 335.7 V; overshoot after
hand-over 6.0 V; settled within 1 % after 1.7 ms; shutdown command at 120 ms, ramp 11.25 ms from 22.5 deg,
all gates off from 131.26 ms (the period after the ramp reaches zero), C2 then discharges through the load.

## 7. Closed-loop host simulation results (cycle-averaged plant)

| Event (nominal scenario) | Result |
| --- | --- |
| load step 25 % -> 100 % | 15.0 V (3.7 %) dip, back within 1 % after 2.0 ms, zero steady-state error |
| set-point 400 -> 380 V (20 V/ms) | tracks the ramp within 7 V, no overshoot beyond 4.2 V |
| load release 100 % -> 0 | 19.7 V (5.2 %) overshoot, within 1 % after 3.4 ms |
| power reversal (12.5 A injected, 5 kW) | phi settles at -10.8 deg, v2 held within 10.4 V (2.7 %) |
| return to forward full load (36 A change) | 28.8 V (7.6 %) dip, within 1 % after 2.4 ms |
| overload 133 % | i_ref clamped at 30.0 A, i2 <= 30.0 A, phi = 27.97 deg, v2 droops to 361.7 V (current limit) |
| controlled shutdown | phase ramp to zero in 11.25 ms, gates off |
| Fault scenario: output short (0.3 Ohm) | under-voltage trip 40 us after the short (v2 = 288.8 V), gates off and latched; short removed, reset accepted, restart rejected by the precharge interlock |
| Input-sag scenario: V1 800 -> 450 V at full load | phase shift driven to 43.9 deg, series-current peak 40.18 A > 40 A -> over-current trip 0.26 ms after the sag, latch holds when the source recovers |

No trip occurs in the nominal scenario; v2 stays within 351-406 V in RUN; the maximum quasi-static
series-current peak is 29.1 A. Traces are stored as `WaveformDataset` HDF5 files with hashes next to
`summary.json`; figures `closed_loop_<scenario>.png` and `gate_pattern.png` follow the repository plot style.

## 8. Verification against ngspice (Level 1 switching model)

`aipe-sim control verify --out DIR` runs the ideal Level 1 model (`aipe_simulation.dab`, stiff
voltage-source ports, 12 cycles, t_max = T/200, analytic initial series current) and compares the
steady-state power with the plant law. Executed with ngspice 47 on Windows (test `tests/test_control_ngspice.py`,
marker `solver`, skipped without ngspice):

| phi (deg) | P plant (W) | P2 ngspice (W) | err P2 (%) | P1 ngspice (W) | err P1 (%) | i_L RMS plant (A) | i_L RMS ngspice (A) | err (%) | phi measured (deg) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 4797.2 | 4796.0 | -0.025 | 4797.1 | -0.001 | 6.231 | 6.233 | +0.033 | 10.000 |
| 22.5 | 10000.0 | 9995.5 | -0.045 | 10001.0 | +0.010 | 13.678 | 13.680 | +0.018 | 22.500 |
| 35 | 14321.0 | 14311.2 | -0.068 | 14323.8 | +0.020 | 20.732 | 20.734 | +0.009 | 35.000 |

The Level 1 netlist includes 20 mOhm series resistance and 1 mOhm switch on-resistance, so the ngspice
output power lies slightly below the lossless law and the error grows with current, as expected. The
agreement validates the static plant gain used for both loop designs; it does not validate the dynamic
assumptions (section 10).

## 9. Future work (explicitly out of scope of this baseline)

- Extended/dual/triple phase-shift modulation (EPS/DPS/TPS) for light-load ZVS and wide voltage range.
- Inverse-law feedforward (phi from the current reference) to remove the plant-gain variation with phi.
- Start-up from 0 V output (diode-rectifier/precharge mode) and burst mode at light load.
- Sensor, ADC/SDFM and gate-driver propagation models; fixed-point/per-unit scaling and code generation.
- Closed-loop verification with the switching model (ngspice co-simulation or Level 2 with C2 and load).

## 10. Hardware aspects not verified

- No firmware was built, flashed or profiled; ISR execution times, interrupt latency and the TBCLK/HRPWM
  step of a specific controller are assumptions (the 100 MHz clock and 150 ps fine step are modelling
  choices consistent with TI's TBPRD = 500, not TI statements).
- No measurement of the loop gains (SFRA), of the phase-register step size or of the dead-band placement.
- The plant is lossless and cycle-averaged: switching losses, dead-time voltage loss, magnetising current,
  series-current dynamics inside a period, sensor dynamics, ADC quantisation and noise are absent; loop
  margins are therefore model margins.
- Protection latency: hardware comparators trip inside the period; the model uses a quasi-static
  series-current estimate with one period of latency and does not represent a hard short-circuit current
  transient (the under-voltage protection trips first in the model).
- Gate-driver interlocks, DESAT detection, relay sequencing, isolation and EMC aspects are outside the scope.
- TI figures are quoted from TI's published documents for TI's operating point and have not been
  re-measured by AIPE.
