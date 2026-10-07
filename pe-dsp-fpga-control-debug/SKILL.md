---
name: pe-dsp-fpga-control-debug
description: Use this skill for power electronics digital control implementation and debugging on DSP, MCU, FPGA, or high-speed FPGA platforms, including control-loop porting, ADC/PWM timing, interrupt scheduling, fixed-point scaling, HDL pipeline latency, protection logic, and hardware bring-up waveform diagnosis.
---

# DSP And FPGA Power Electronics Control Debugging

## Accessibility

Tool and hardware access depends on the chosen execution variant. Open timing/numerical checks are possible; target hardware, debug probes and compiler/FPGA tool licences vary.

## Goal

Use this skill to help power electronics engineers move control algorithms from simulation into DSP, MCU, FPGA, or high-speed FPGA implementations. The priority is to find timing, scaling, sampling, PWM, protection, and implementation issues that make real digital control behave differently from the model.

## Classify The Implementation Problem

When a request arrives, first classify it:

- DSP/MCU control porting: C implementation, ISR timing, ADC trigger, PWM update, peripheral configuration, and protection interrupts.
- FPGA control implementation: HDL pipeline latency, clock-domain crossing, fixed-point datapath, PWM generation, ADC interface, and deterministic protection logic.
- Fixed-point and scaling: coefficient quantization, overflow, saturation, normalization, signed/unsigned mismatch, and limit handling.
- Timing mismatch: sampling instant, computation delay, PWM shadow-load timing, interrupt jitter, DMA latency, and multi-rate scheduling.
- Hardware bring-up fault: abnormal waveform, duty command railed, current sense offset, trip-zone event, ADC noise, or protection latch.
- Simulation-to-hardware mismatch: controller works in PLECS/Simulink/LTspice but fails on the target processor or FPGA.

## Ask For Missing Inputs

Ask only for information that materially changes the diagnosis:

- Control platform: DSP/MCU family, FPGA family, clock frequency, ADC/PWM peripherals, and toolchain if known.
- Topology, control method, switching frequency, sample frequency, and PWM update mode.
- Data format: floating point, fixed point, Q format, HDL word lengths, scaling, and saturation policy.
- Timing path: ADC trigger, conversion complete, ISR or HDL pipeline, control calculation, PWM shadow load, and gate update.
- Symptom: abnormal waveforms, trip flags, duty/frequency command, current/voltage sample, and whether the issue appears at startup, load step, or a specific operating point.

## References

Load only what is needed:

- DSP/MCU implementation workflow: `references/dsp-implementation-workflow.md`
- FPGA/high-speed FPGA control workflow: `references/fpga-control-workflow.md`
- Fixed-point, scaling, and latency checklist: `references/fixed-point-timing-checklist.md`
- Hardware bring-up and waveform diagnosis: `references/bring-up-debug-checklist.md`

## Default Answer Structure

1. Symptom restatement: state what works in simulation, what fails on the target, and the operating condition.
2. Implementation path map: describe ADC sampling, control calculation, delay, PWM update, and protection timing.
3. Ranked hypotheses: classify likely causes as timing, scaling, peripheral configuration, HDL datapath, protection, or analog sensing.
4. Checks to run: provide register/peripheral checks, waveform probes, logging points, fixed-point tests, or HDL simulation checks.
5. Key signals: list ADC samples, error signal, controller output, duty command, PWM compare, gate output, trip flags, and measured power-stage waveforms.
6. Next experiment: give the smallest action that can separate algorithm error from implementation or hardware error.
