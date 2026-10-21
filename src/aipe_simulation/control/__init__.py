"""Digital single-phase-shift (SPS) control baseline for the AIPE 10 kW DAB.

Modules
-------
``sps_modulator``
    Discrete SPS modulator: command limiting, slew limiting, timer
    quantisation (coarse clock + high-resolution step), shadow-register update
    per switching period, dead-time insertion, leg-to-leg 180 degree
    synchronisation and the eight gate signals; sign convention identical to
    :mod:`aipe_simulation.dab.gating` (``phi > 0``: secondary lags, power 1 -> 2).
``plant``
    Cycle-averaged sampled-data model of the DAB output port (lossless SPS
    power law, port-2 capacitor with resistive/current-source load, optional
    source resistance) with its small-signal linearisation.
``controllers``
    Discrete PI and 2P2Z (DF22) compensators with saturation and anti-windup,
    design rules from a crossover/phase-margin target and z-plane loop analysis
    (crossover frequency, phase and gain margins) including computation and
    measurement delays.
``simulate``
    Closed-loop host simulation (start-up, load step, set-point change, power
    reversal, current limit, fault trip with latch, shutdown) producing JSON,
    HDF5 traces and matplotlib figures.
``verify``
    Steady-state power comparison between the cycle-averaged plant and the
    executed ngspice Level 1 switching model.

Everything here is a host-side model: no firmware was built or executed on a
controller target. TI's TIDA-010054 figures quoted in the documentation are
TI's published values, not AIPE results.
"""

from .controllers import Df22Compensator, DiscretePI, design_2p2z, design_pi_for_static_plant, stability_margins  # noqa: F401
from .plant import DabSpsPlant, DabSpsPlantParameters, sps_output_current, sps_power  # noqa: F401
from .sps_modulator import PhaseRegister, SpsModulator, SpsModulatorConfig  # noqa: F401
from .ztf import ZTransfer  # noqa: F401
