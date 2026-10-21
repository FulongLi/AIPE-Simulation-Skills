"""Single-phase-shift (SPS) gate timing for the eight DAB switches.

Each switch conducts for ``T/2 - t_dead`` per period. Leg transitions happen at
the ideal switching instants; with dead time, the outgoing switch turns off
``t_dead/2`` before and the incoming switch turns on ``t_dead/2`` after that
instant. Time origin: centre of the primary positive half-cycle (S1, S4 on).

Ideal switching instants
------------------------
* primary (``v_ab`` edges):   ``t = T/4 + k T/2``; rising (-V1 -> +V1) at ``3T/4 + kT``,
  falling at ``T/4 + kT``.
* secondary (``v_cd`` edges): the same shifted by ``t_phi``.

Switch roles
------------
S1 high-side leg A, S2 low-side leg A, S3 high-side leg B, S4 low-side leg B,
S5 high-side leg C, S6 low-side leg C, S7 high-side leg D, S8 low-side leg D.
S1 and S4 share the primary "positive" pattern, S2 and S3 the complementary
pattern; S5 and S8 share the secondary positive pattern, S6 and S7 the
complement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SWITCHES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")
LEG_OF = {"S1": "A", "S2": "A", "S3": "B", "S4": "B", "S5": "C", "S6": "C", "S7": "D", "S8": "D"}
HIGH_SIDE = {"S1", "S3", "S5", "S7"}
PRIMARY = {"S1", "S2", "S3", "S4"}


@dataclass(frozen=True)
class PulseSpec:
    """Parameters of an ngspice ``PULSE(v_initial v_pulse td tr tf pw per)`` source."""

    v_initial: float
    v_pulse: float
    td: float
    tr: float
    tf: float
    pw: float
    per: float

    def spice(self) -> str:
        return (f"PULSE({self.v_initial:g} {self.v_pulse:g} {self.td:.12g} {self.tr:.3g} "
                f"{self.tf:.3g} {self.pw:.12g} {self.per:.12g})")


@dataclass(frozen=True)
class SpsTiming:
    f_sw: float
    phi_rad: float
    dead_time: float = 0.0
    gate_voltage: float = 15.0
    edge_time: float = 1e-9

    @property
    def period(self) -> float:
        return 1.0 / self.f_sw

    @property
    def t_phi(self) -> float:
        return self.phi_rad / (2 * math.pi) * self.period

    @property
    def on_duration(self) -> float:
        return self.period / 2 - self.dead_time

    def on_start(self, switch: str) -> float:
        """Start of the first on-interval (may be negative), before wrapping."""
        T = self.period
        base = -T / 4 if switch in ("S1", "S4", "S5", "S8") else T / 4
        shift = 0.0 if switch in PRIMARY else self.t_phi
        return base + self.dead_time / 2 + shift

    def rising_edges(self, switch: str, t_end: float, t_start: float = 0.0) -> list[float]:
        """Gate turn-on instants within [t_start, t_end]."""
        return self._edges(self.on_start(switch), t_start, t_end)

    def falling_edges(self, switch: str, t_end: float, t_start: float = 0.0) -> list[float]:
        """Gate turn-off instants within [t_start, t_end]."""
        return self._edges(self.on_start(switch) + self.on_duration, t_start, t_end)

    def _edges(self, first: float, t_start: float, t_end: float) -> list[float]:
        T = self.period
        k0 = math.floor((t_start - first) / T) - 1
        edges = []
        k = k0
        while True:
            t = first + k * T
            if t > t_end + 1e-15:
                break
            if t >= t_start - 1e-15:
                edges.append(t)
            k += 1
        return edges

    def ideal_switching_instants(self, bridge: str, t_end: float, t_start: float = 0.0) -> list[dict]:
        """Bridge voltage transitions (centre of the dead band) with their direction.

        ``bridge`` is ``"primary"`` or ``"secondary"``. Each entry is
        ``{"t": time, "direction": +1 for -V -> +V, -1 for +V -> -V}``.
        """
        T = self.period
        shift = 0.0 if bridge == "primary" else self.t_phi
        out = []
        for first, direction in ((T / 4 + shift, -1), (3 * T / 4 + shift, +1)):
            for t in self._edges(first, t_start, t_end):
                out.append({"t": t, "direction": direction})
        out.sort(key=lambda e: e["t"])
        return out

    def gate_pulse(self, switch: str) -> PulseSpec:
        """ngspice PULSE parameters reproducing this switch's periodic gate signal.

        The square wave has period ``T`` and on-duration ``T/2 - t_dead``; the
        first rising and falling edges inside ``[0, T)`` decide whether the pulse
        starts high or low, so arbitrary (also negative) phase shifts are exact.
        """
        T = self.period
        r0 = self.on_start(switch) % T
        f0 = (self.on_start(switch) + self.on_duration) % T
        vg, te = self.gate_voltage, self.edge_time
        # PULSE delays mark the start of an edge; subtract half an edge so that the
        # mid-threshold crossing coincides with the ideal instant (clamped at t = 0,
        # which only affects an edge inside the first few nanoseconds of the run).
        if r0 < f0:  # initially off, pulse high between r0 and f0
            return PulseSpec(0.0, vg, max(r0 - te / 2, 0.0), te, te, max(f0 - r0 - te, te), T)
        # initially on, pulse low between f0 and r0
        return PulseSpec(vg, 0.0, max(f0 - te / 2, 0.0), te, te, max(r0 - f0 - te, te), T)

    def describe(self) -> dict:
        return {
            "modulation": "single-phase-shift",
            "time_origin": "centre of primary positive half-cycle (S1, S4 on)",
            "period_s": self.period,
            "phi_rad": self.phi_rad,
            "phi_deg": math.degrees(self.phi_rad),
            "t_phi_s": self.t_phi,
            "dead_time_s": self.dead_time,
            "on_duration_s": self.on_duration,
            "sign_convention": "phi > 0: secondary lags primary, power flows from port 1 to port 2",
            "switch_roles": {s: {"leg": LEG_OF[s], "side": "high" if s in HIGH_SIDE else "low",
                                 "bridge": "primary" if s in PRIMARY else "secondary"} for s in SWITCHES},
            "gate_pulses": {s: self.gate_pulse(s).spice() for s in SWITCHES},
        }
