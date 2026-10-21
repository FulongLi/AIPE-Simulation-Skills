"""Waveform dataset with time coordinate, units, provenance and HDF5 persistence.

HDF5 layout (``format`` attribute ``aipe-waveform-dataset/0.1``)::

    /time                      float64 [s]
    /channels/<name>           float64, attrs: unit, description, sign_convention
    attrs: format, metadata (JSON string), sha256 of (time + channel data)

Large arrays stay in the HDF5 file; language-model agents receive the JSON
summary and a reference (path + hash) to the dataset.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Union

import numpy as np

FORMAT = "aipe-waveform-dataset/0.1"


@dataclass
class Channel:
    name: str
    data: np.ndarray
    unit: str
    description: str = ""
    sign_convention: str = ""


@dataclass
class WaveformDataset:
    time: np.ndarray
    channels: dict[str, Channel] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ---- construction -------------------------------------------------------
    def add(self, name: str, data: np.ndarray, unit: str, description: str = "", sign_convention: str = "") -> Channel:
        data = np.asarray(data, dtype=np.float64)
        if data.shape != self.time.shape:
            raise ValueError(f"channel {name}: shape {data.shape} differs from time {self.time.shape}")
        if not np.all(np.isfinite(data)):
            raise ValueError(f"channel {name} contains non-finite samples")
        channel = Channel(name, data, unit, description, sign_convention)
        self.channels[name] = channel
        return channel

    def get(self, name: str) -> np.ndarray:
        return self.channels[name].data

    def __contains__(self, name: str) -> bool:
        return name in self.channels

    def __iter__(self) -> Iterator[Channel]:
        return iter(self.channels.values())

    @property
    def n_points(self) -> int:
        return int(self.time.shape[0])

    def window(self, t0: float, t1: float) -> "WaveformDataset":
        """Return the samples with ``t0 <= t <= t1`` (inclusive)."""
        mask = (self.time >= t0 - 1e-15) & (self.time <= t1 + 1e-15)
        sub = WaveformDataset(self.time[mask], {}, dict(self.metadata))
        for channel in self:
            sub.channels[channel.name] = Channel(channel.name, channel.data[mask], channel.unit,
                                                 channel.description, channel.sign_convention)
        sub.metadata["window"] = {"t0": float(t0), "t1": float(t1)}
        return sub

    def timestep_statistics(self) -> dict:
        dt = np.diff(self.time)
        if dt.size == 0:
            return {"n_points": self.n_points}
        return {"n_points": self.n_points, "dt_min": float(dt.min()), "dt_max": float(dt.max()),
                "dt_mean": float(dt.mean()), "dt_median": float(np.median(dt)),
                "t_start": float(self.time[0]), "t_end": float(self.time[-1])}

    # ---- integrity ----------------------------------------------------------
    def sha256(self) -> str:
        digest = hashlib.sha256()
        digest.update(np.ascontiguousarray(self.time, dtype=np.float64).tobytes())
        for name in sorted(self.channels):
            digest.update(name.encode("utf-8"))
            digest.update(np.ascontiguousarray(self.channels[name].data, dtype=np.float64).tobytes())
        return digest.hexdigest()

    # ---- persistence --------------------------------------------------------
    def save_hdf5(self, path: Union[str, Path], compression: Union[str, None] = "gzip") -> str:
        import h5py

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(path, "w") as handle:
            handle.attrs["format"] = FORMAT
            handle.attrs["metadata"] = json.dumps(self.metadata, sort_keys=True, default=_json_default)
            handle.attrs["sha256"] = self.sha256()
            time_ds = handle.create_dataset("time", data=self.time, compression=compression)
            time_ds.attrs["unit"] = "s"
            group = handle.create_group("channels")
            for name in sorted(self.channels):
                channel = self.channels[name]
                ds = group.create_dataset(name, data=channel.data, compression=compression)
                ds.attrs["unit"] = channel.unit
                ds.attrs["description"] = channel.description
                ds.attrs["sign_convention"] = channel.sign_convention
        return str(path)

    @classmethod
    def load_hdf5(cls, path: Union[str, Path]) -> "WaveformDataset":
        import h5py

        with h5py.File(path, "r") as handle:
            if handle.attrs.get("format") != FORMAT:
                raise ValueError(f"unsupported waveform dataset format: {handle.attrs.get('format')!r}")
            dataset = cls(np.array(handle["time"][...], dtype=np.float64), {}, json.loads(handle.attrs["metadata"]))
            for name, ds in handle["channels"].items():
                dataset.channels[name] = Channel(name, np.array(ds[...], dtype=np.float64), str(ds.attrs.get("unit", "")),
                                                 str(ds.attrs.get("description", "")), str(ds.attrs.get("sign_convention", "")))
            stored = handle.attrs.get("sha256")
        if stored and stored != dataset.sha256():
            raise ValueError("waveform dataset hash mismatch: file content was modified")
        return dataset

    def channel_index(self) -> list[dict]:
        return [{"name": c.name, "unit": c.unit, "description": c.description, "sign_convention": c.sign_convention}
                for c in sorted(self.channels.values(), key=lambda c: c.name)]


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")
