"""WaveformDataset construction, windowing, statistics and HDF5 persistence with integrity hash."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from aipe_simulation.waveforms.dataset import FORMAT, Channel, WaveformDataset

F = 1e3
T = 1.0 / F


@pytest.fixture
def dataset() -> WaveformDataset:
    t = np.linspace(0.0, 1e-3, 101)
    ds = WaveformDataset(t, {}, {"spec": {"name": "unit", "f_sw": F}, "tags": ["a", "b"], "n": 3})
    ds.add("v_out", 5.0 * np.sin(2 * np.pi * F * t), "V", "output voltage", "node to ground")
    ds.add("i_l", np.cos(2 * np.pi * F * t), "A", "inductor current")
    return ds


def test_add_and_get(dataset):
    ch = dataset.channels["v_out"]
    assert isinstance(ch, Channel)
    assert (ch.name, ch.unit, ch.description, ch.sign_convention) == ("v_out", "V", "output voltage", "node to ground")
    assert dataset.channels["i_l"].sign_convention == ""
    assert dataset.get("v_out") is ch.data
    assert "v_out" in dataset and "i_l" in dataset and "missing" not in dataset
    assert [c.name for c in dataset] == ["v_out", "i_l"]
    assert dataset.n_points == 101
    added = dataset.add("ramp", np.arange(101), "1")
    assert isinstance(added, Channel) and added.data.dtype == np.float64
    assert dataset.get("ramp")[-1] == 100.0
    dataset.add("ramp", list(range(101)), "V")  # re-adding replaces
    assert dataset.channels["ramp"].unit == "V"
    with pytest.raises(KeyError):
        dataset.get("missing")


def test_rejects_wrong_shapes_and_non_finite_samples(dataset):
    with pytest.raises(ValueError, match="shape"):
        dataset.add("bad", np.zeros(50), "V")
    with pytest.raises(ValueError, match="shape"):
        dataset.add("bad", np.zeros((101, 1)), "V")
    nan = np.zeros(101)
    nan[7] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        dataset.add("bad", nan, "V")
    inf = np.zeros(101)
    inf[0] = -np.inf
    with pytest.raises(ValueError, match="non-finite"):
        dataset.add("bad", inf, "V")
    assert "bad" not in dataset


def test_window_is_inclusive_and_copies_metadata(dataset):
    sub = dataset.window(2e-4, 5e-4)
    assert sub.n_points == 31
    assert sub.time[0] == pytest.approx(2e-4, abs=1e-15)
    assert sub.time[-1] == pytest.approx(5e-4, abs=1e-15)
    mask = (dataset.time >= 2e-4 - 1e-15) & (dataset.time <= 5e-4 + 1e-15)
    for channel in dataset:
        sub_channel = sub.channels[channel.name]
        np.testing.assert_array_equal(sub_channel.data, channel.data[mask])
        assert (sub_channel.unit, sub_channel.description, sub_channel.sign_convention) == (
            channel.unit, channel.description, channel.sign_convention)
    assert sub.metadata["window"] == {"t0": 2e-4, "t1": 5e-4}
    assert "window" not in dataset.metadata
    assert sub.metadata["spec"] == dataset.metadata["spec"]
    assert dataset.window(5e-4, 2e-4).n_points == 0
    assert dataset.window(0.0, 1e-3).n_points == dataset.n_points


def test_timestep_statistics(dataset):
    st = dataset.timestep_statistics()
    assert st["n_points"] == 101
    assert st["dt_min"] == pytest.approx(1e-5, rel=1e-9)
    assert st["dt_max"] == pytest.approx(1e-5, rel=1e-9)
    assert st["dt_mean"] == pytest.approx(1e-5, rel=1e-9)
    assert st["dt_median"] == pytest.approx(1e-5, rel=1e-9)
    assert st["t_start"] == 0.0 and st["t_end"] == pytest.approx(1e-3)
    irregular = WaveformDataset(np.array([0.0, 1.0, 3.0, 6.0, 10.0]))
    st = irregular.timestep_statistics()
    assert (st["dt_min"], st["dt_max"], st["dt_mean"], st["dt_median"]) == (1.0, 4.0, 2.5, 2.5)
    assert (st["t_start"], st["t_end"], st["n_points"]) == (0.0, 10.0, 5)
    assert WaveformDataset(np.array([0.0])).timestep_statistics() == {"n_points": 1}


def test_sha256_depends_on_data_and_names_but_not_insertion_order(dataset):
    digest = dataset.sha256()
    assert len(digest) == 64 and digest == dataset.sha256()
    reordered = WaveformDataset(dataset.time.copy(), {}, {})
    reordered.add("i_l", dataset.get("i_l").copy(), "A")
    reordered.add("v_out", dataset.get("v_out").copy(), "V")
    assert reordered.sha256() == digest  # units/metadata are not part of the hash; names and data are
    modified = WaveformDataset(dataset.time.copy(), {}, {})
    modified.add("i_l", dataset.get("i_l").copy(), "A")
    data = dataset.get("v_out").copy()
    data[5] += 1e-9
    modified.add("v_out", data, "V")
    assert modified.sha256() != digest
    renamed = WaveformDataset(dataset.time.copy(), {}, {})
    renamed.add("i_l", dataset.get("i_l").copy(), "A")
    renamed.add("v_out2", dataset.get("v_out").copy(), "V")
    assert renamed.sha256() != digest


@pytest.mark.parametrize("compression", ["gzip", None])
def test_hdf5_round_trip(dataset, tmp_path, compression):
    path = tmp_path / "wf.h5"
    assert dataset.save_hdf5(path, compression=compression) == str(path)
    loaded = WaveformDataset.load_hdf5(path)
    np.testing.assert_array_equal(loaded.time, dataset.time)
    assert set(loaded.channels) == set(dataset.channels)
    for name, channel in dataset.channels.items():
        got = loaded.channels[name]
        np.testing.assert_array_equal(got.data, channel.data)
        assert got.data.dtype == np.float64
        assert (got.unit, got.description, got.sign_convention) == (channel.unit, channel.description, channel.sign_convention)
    assert loaded.metadata == dataset.metadata
    assert loaded.sha256() == dataset.sha256()
    with h5py.File(path, "r") as handle:
        assert handle.attrs["format"] == FORMAT
        assert handle.attrs["sha256"] == dataset.sha256()
        assert handle["time"].attrs["unit"] == "s"
        assert handle["channels/v_out"].attrs["unit"] == "V"
        assert handle["channels/v_out"].compression == compression
        assert sorted(handle["channels"]) == ["i_l", "v_out"]


def test_load_detects_tampered_channel(dataset, tmp_path):
    path = tmp_path / "wf.h5"
    dataset.save_hdf5(path)
    WaveformDataset.load_hdf5(path)  # intact file loads
    with h5py.File(path, "r+") as handle:
        handle["channels/v_out"][10] = handle["channels/v_out"][10] + 1e-3
    with pytest.raises(ValueError, match="hash mismatch"):
        WaveformDataset.load_hdf5(path)


def test_load_detects_tampered_time_axis(dataset, tmp_path):
    path = tmp_path / "wf.h5"
    dataset.save_hdf5(path)
    with h5py.File(path, "r+") as handle:
        handle["time"][-1] = handle["time"][-1] * 1.0001
    with pytest.raises(ValueError, match="hash mismatch"):
        WaveformDataset.load_hdf5(path)


def test_load_rejects_foreign_format(tmp_path):
    path = tmp_path / "foreign.h5"
    with h5py.File(path, "w") as handle:
        handle.attrs["format"] = "something-else/9"
        handle.create_dataset("time", data=np.arange(3.0))
    with pytest.raises(ValueError, match="unsupported waveform dataset format"):
        WaveformDataset.load_hdf5(path)
    bare = tmp_path / "bare.h5"
    with h5py.File(bare, "w") as handle:
        handle.create_dataset("time", data=np.arange(3.0))
    with pytest.raises(ValueError, match="unsupported waveform dataset format"):
        WaveformDataset.load_hdf5(bare)


def test_channel_index(dataset):
    index = dataset.channel_index()
    assert [c["name"] for c in index] == ["i_l", "v_out"]
    assert index[1] == {"name": "v_out", "unit": "V", "description": "output voltage", "sign_convention": "node to ground"}


def test_metadata_with_numpy_and_path_values_is_serialised(tmp_path):
    t = np.linspace(0.0, 1.0, 5)
    ds = WaveformDataset(t, {}, {"np_int": np.int64(3), "np_float": np.float64(1.5), "arr": np.arange(3), "path": Path("x/y")})
    ds.add("x", t, "s")
    path = tmp_path / "meta.h5"
    ds.save_hdf5(path)
    loaded = WaveformDataset.load_hdf5(path)
    assert loaded.metadata == {"np_int": 3, "np_float": 1.5, "arr": [0, 1, 2], "path": "x/y"} or loaded.metadata["path"] == "x\\y"
    assert loaded.metadata["np_int"] == 3 and loaded.metadata["arr"] == [0, 1, 2]
    bad = WaveformDataset(t, {}, {"unserialisable": {1, 2}})
    with pytest.raises(TypeError, match="not JSON serialisable"):
        bad.save_hdf5(tmp_path / "bad.h5")
