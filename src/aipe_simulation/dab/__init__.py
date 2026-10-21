"""Dual-active-bridge switching-circuit generation and execution for ngspice.

Conventions (shared by :mod:`gating`, :mod:`netlist` and the waveform analysis):

* Port 1 (primary) DC source ``V1`` between ``p_pos`` and ground; port 2
  (secondary) DC port ``V2`` between ``s_pos`` and ground. Both DC negatives are
  tied to the SPICE ground node; the ideal transformer (``E``/``F`` sources) has no
  galvanic path, so this only provides the DC reference SPICE requires.
* Primary bridge legs A (S1 high, S2 low, mid-node ``a``) and B (S3 high, S4 low,
  mid-node ``b``); ``v_ab = v(a) - v(b)``; S1 and S4 conducting gives ``+V1``.
* Secondary bridge legs C (S5 high, S6 low, ``c``) and D (S7 high, S8 low, ``d``);
  ``v_cd = v(c) - v(d)``; S5 and S8 conducting gives ``+V2``.
* Turns ratio ``n = N_p / N_s``; primary-referred secondary voltage ``n * v_cd``.
* Series current ``i_L`` flows from node ``a`` through the external inductance
  towards the transformer; secondary current ``i_s`` flows out of the transformer
  secondary into node ``c``.
* Phase shift ``phi > 0`` means the secondary bridge lags the primary bridge and
  power flows from port 1 to port 2. ``phi`` is in electrical radians of the
  switching period (``t_phi = phi / (2 pi) * T``).
* Time origin ``t = 0`` is the centre of the primary positive half-cycle (S1 and
  S4 on). This "centred" gating starts the magnetising current at its zero
  crossing so that no DC magnetising offset is introduced by the start-up.
* Per-switch currents ``i_Sk`` are positive for drain-to-source (forward channel)
  conduction and negative for reverse conduction (channel or antiparallel diode).
"""

from .spec import DabCircuitSpec  # noqa: F401
from .gating import SpsTiming, PulseSpec  # noqa: F401
from .netlist import build_dab_netlist  # noqa: F401
from .run import run_dab, DabRunResult  # noqa: F401
