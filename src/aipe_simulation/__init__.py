"""Executable simulation capabilities for AIPE (AI for Power Engineering).

Subpackages
-----------
``aipe_simulation.ngspice``
    Locate and qualify an ngspice installation, run batch netlists, parse raw
    output files. ngspice is the primary open-source switching-circuit solver.
``aipe_simulation.dab``
    Dual-active-bridge (DAB) circuit generation: typed circuit specification,
    single-phase-shift (SPS) eight-switch gate timing and ngspice netlists for
    the ideal (Level 1) and non-ideal (Level 2) models, plus an end-to-end runner.
``aipe_simulation.waveforms``
    Solver-independent waveform dataset (HDF5 + JSON), steady-state window
    identification and engineering metrics consumed by downstream specialist
    agents (semiconductor losses, magnetics, thermal, control).
``aipe_simulation.control``
    Digital SPS control baseline: discrete modulator model (limits, slew,
    timer quantisation, dead time, eight gate signals), cycle-averaged
    sampled-data plant, PI / 2P2Z compensators with z-plane loop analysis,
    closed-loop host simulation and a verification of the plant against the
    executed ngspice Level 1 model.

Nothing in this package fabricates solver results: every numerical quantity is
derived from an executed solver run, and a run that failed, did not converge or
did not reach periodic steady state is reported as such.
"""

__version__ = "0.2.0"
