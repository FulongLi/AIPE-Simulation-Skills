"""Minimal z-domain transfer-function arithmetic (numpy only).

Coefficients are stored in ascending powers of ``z^-1``::

    H(z) = (b[0] + b[1] z^-1 + b[2] z^-2 + ...) / (1 + a[1] z^-1 + a[2] z^-2 + ...)

which is the natural form of a difference equation
``y[k] = sum_i b[i] u[k-i] - sum_{i>=1} a[i] y[k-i]`` and of the direct-form
compensators (DF22) used in digital power controllers. The class offers the
few operations needed for loop analysis: series/parallel connection, unit
delays, closed-loop (feedback) composition, frequency response on the unit
circle, poles/zeros and time-domain simulation. Common factors are not
cancelled; this is harmless for the margin and stability checks performed
here because every factor introduced by ``feedback`` is stable by construction.
"""

from __future__ import annotations

from typing import Iterable, Union

import numpy as np

Number = Union[int, float]


class ZTransfer:
    """Rational transfer function in ``z^-1`` with real coefficients."""

    __array_priority__ = 1000  # make numpy scalars defer to our operators

    def __init__(self, num: Iterable[float], den: Iterable[float] = (1.0,)):
        num = np.atleast_1d(np.asarray(num, dtype=np.float64))
        den = np.atleast_1d(np.asarray(den, dtype=np.float64))
        if den.size == 0 or den[0] == 0.0:
            raise ValueError("denominator must start with a non-zero coefficient")
        if not (np.all(np.isfinite(num)) and np.all(np.isfinite(den))):
            raise ValueError("coefficients must be finite")
        self.num = _trim(num / den[0])
        self.den = _trim(den / den[0])

    # ---- constructors -------------------------------------------------------
    @classmethod
    def gain(cls, k: float) -> "ZTransfer":
        return cls([float(k)], [1.0])

    @classmethod
    def delay(cls, samples: int) -> "ZTransfer":
        """Pure delay ``z^-samples`` (``samples >= 0``)."""
        if samples < 0:
            raise ValueError("delay must be non-negative")
        return cls([0.0] * int(samples) + [1.0], [1.0])

    # ---- evaluation ---------------------------------------------------------
    def __call__(self, z):
        """Evaluate at complex ``z`` (scalar or array)."""
        z = np.asarray(z, dtype=np.complex128)
        zi = 1.0 / z
        num = sum(b * zi ** i for i, b in enumerate(self.num))
        den = sum(a * zi ** i for i, a in enumerate(self.den))
        return num / den

    def freqresp(self, f_hz, ts: float):
        """Frequency response at frequencies ``f_hz`` for sampling period ``ts``."""
        f = np.asarray(f_hz, dtype=np.float64)
        return self(np.exp(1j * 2 * np.pi * f * ts))

    def dc_gain(self) -> float:
        with np.errstate(divide="ignore", invalid="ignore"):
            value = complex(self(1.0 + 0j))
        return float(value.real) if np.isfinite(value.real) else float("inf")

    # ---- algebra ------------------------------------------------------------
    def _coerce(self, other) -> "ZTransfer":
        if isinstance(other, ZTransfer):
            return other
        if isinstance(other, (int, float, np.integer, np.floating)):
            return ZTransfer.gain(float(other))
        return NotImplemented

    def __mul__(self, other):
        other = self._coerce(other)
        if other is NotImplemented:
            return NotImplemented
        return ZTransfer(np.convolve(self.num, other.num), np.convolve(self.den, other.den))

    __rmul__ = __mul__

    def __add__(self, other):
        other = self._coerce(other)
        if other is NotImplemented:
            return NotImplemented
        num = _padd(np.convolve(self.num, other.den), np.convolve(other.num, self.den))
        return ZTransfer(num, np.convolve(self.den, other.den))

    __radd__ = __add__

    def __neg__(self):
        return ZTransfer(-self.num, self.den)

    def __sub__(self, other):
        other = self._coerce(other)
        if other is NotImplemented:
            return NotImplemented
        return self + (-other)

    def __rsub__(self, other):
        other = self._coerce(other)
        if other is NotImplemented:
            return NotImplemented
        return other + (-self)

    def __truediv__(self, other):
        other = self._coerce(other)
        if other is NotImplemented:
            return NotImplemented
        if other.num[0] == 0.0:
            raise ZeroDivisionError("cannot invert a transfer function with a leading zero (pure delay)")
        return ZTransfer(np.convolve(self.num, other.den), np.convolve(self.den, other.num))

    def delayed(self, samples: int) -> "ZTransfer":
        return self * ZTransfer.delay(samples)

    def feedback(self, other=1.0) -> "ZTransfer":
        """Closed loop ``H / (1 + H * other)`` (negative feedback through ``other``)."""
        other = self._coerce(other)
        if other is NotImplemented:
            raise TypeError("feedback path must be a number or a ZTransfer")
        num = np.convolve(self.num, other.den)
        den = _padd(np.convolve(self.den, other.den), np.convolve(self.num, other.num))
        return ZTransfer(num, den)

    # ---- poles and zeros ----------------------------------------------------
    def poles(self) -> np.ndarray:
        # a[0] + a[1] z^-1 + ... = z^-(m) (a[0] z^m + a[1] z^(m-1) + ...): roots of the descending polynomial a.
        return np.roots(self.den) if self.den.size > 1 else np.array([], dtype=np.complex128)

    def zeros(self) -> np.ndarray:
        return np.roots(self.num) if self.num.size > 1 else np.array([], dtype=np.complex128)

    def max_pole_radius(self) -> float:
        poles = self.poles()
        return float(np.max(np.abs(poles))) if poles.size else 0.0

    def is_stable(self, tol: float = 1e-9) -> bool:
        """All poles strictly inside the unit circle (poles on the circle, e.g. integrators, are not stable)."""
        return self.max_pole_radius() < 1.0 - tol

    # ---- time domain --------------------------------------------------------
    def simulate(self, u) -> np.ndarray:
        """Response to the input sequence ``u`` from zero initial conditions."""
        u = np.asarray(u, dtype=np.float64)
        y = np.zeros_like(u)
        b, a = self.num, self.den
        for k in range(u.size):
            acc = 0.0
            for i, bi in enumerate(b):
                if k - i >= 0:
                    acc += bi * u[k - i]
            for i in range(1, a.size):
                if k - i >= 0:
                    acc -= a[i] * y[k - i]
            y[k] = acc
        return y

    def step_response(self, n: int) -> np.ndarray:
        return self.simulate(np.ones(int(n)))

    # ---- serialisation ------------------------------------------------------
    def to_dict(self) -> dict:
        return {"num_z_inverse": [float(v) for v in self.num], "den_z_inverse": [float(v) for v in self.den],
                "convention": "H(z) = sum(num[i] z^-i) / sum(den[i] z^-i), den[0] = 1"}

    def __repr__(self) -> str:
        return f"ZTransfer(num={self.num.tolist()}, den={self.den.tolist()})"


def _trim(coeffs: np.ndarray) -> np.ndarray:
    """Remove trailing (highest-order z^-1) zeros, keeping at least one coefficient."""
    end = coeffs.size
    while end > 1 and coeffs[end - 1] == 0.0:
        end -= 1
    return np.array(coeffs[:end], dtype=np.float64)


def _padd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = max(a.size, b.size)
    out = np.zeros(n)
    out[:a.size] += a
    out[:b.size] += b
    return out
