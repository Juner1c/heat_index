from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from research.phase4.common import FEATURES, load_config
from research.phase4.data.dataset_builder import build_dataset, heat_index_c, make_sequences
from research.phase4.data.temporal_split import chronological_split, sufficiency, walk_forward_splits
from research.phase4.data.validation import audit_csv, normalize_timestamps
from research.phase4.training.scaling import Scaling


@pytest.fixture
def local_sources(tmp_path):
    """Deliberately synthetic software-test fixture, not reported as observations."""
    times = pd.date_range("2024-01-01", periods=96, freq="h", tz="UTC")
    step = np.arange(96)
    satellite = pd.DataFrame({"timestamp": times, **{column: 240+step*.1+i for i, column in enumerate(FEATURES[3:])}})
    weather = pd.DataFrame({"time": times, "temperature_C": 27+np.sin(step/4),
                            "humidity_percent": 75+np.cos(step/4), "dew_point_C": 24.0})
    a, b = tmp_path/"satellite.csv", tmp_path/"weather.csv"
    satellite.to_csv(a, index=False); weather.to_csv(b, index=False)
    return a, b


@pytest.fixture
def sample_data(local_sources):
    frame, manifest = build_dataset([local_sources[0]], [local_sources[1]], {"type": "synthetic_test_fixture"})
    samples = make_sequences(frame, 6)
    return frame, manifest, samples


def test_builder_units_targets_and_repeatable_fingerprint(local_sources, sample_data):
    frame, manifest, samples = sample_data
    repeated, repeated_manifest = build_dataset([local_sources[0]], [local_sources[1]], {"type": "synthetic_test_fixture"})
    assert manifest["dataset_fingerprint"] == repeated_manifest["dataset_fingerprint"]
    assert manifest["valid_one_hour_targets"] == 95
    assert manifest["units"]["B08_mean_K"] == "K"
    np.testing.assert_array_equal(frame[FEATURES].to_numpy(), repeated[FEATURES].to_numpy())
    np.testing.assert_allclose(frame.target_heat_index_1h_C.iloc[:-1], frame.heat_index_C.iloc[1:])
    assert np.isnan(frame.target_heat_index_1h_C.iloc[-1])
    assert len(samples.y) == 90 and samples.x.shape == (90,6,7)
    assert ((samples.targets-samples.origins) == pd.Timedelta(hours=1)).all()
    np.testing.assert_allclose(samples.x[0], frame[FEATURES].iloc[:6])
    assert samples.y[0] == frame.heat_index_C.iloc[6]


def test_utc_conversion_and_invalid_timestamp():
    values = normalize_timestamps(pd.Series(["2024-01-01T08:00:00+08:00", "2024-01-01T00:00:00Z", "2024-01-01 00:00", "bad"]))
    assert values.iloc[0] == values.iloc[1] == values.iloc[2]
    assert pd.isna(values.iloc[3])


def test_duplicates_missing_hours_nonfinite_and_offhour(local_sources):
    satellite, weather = local_sources
    frame = pd.read_csv(satellite)
    frame = pd.concat([frame, frame.iloc[[0]]])
    frame.to_csv(satellite, index=False)
    assert audit_csv(satellite, "timestamp")["duplicate_timestamps"] == 1
    with pytest.raises(ValueError, match="Duplicate"):
        build_dataset([satellite], [weather], {})
    frame = frame.iloc[:-1].drop(index=12)
    frame.loc[20, "B08_mean_K"] = np.inf
    frame.to_csv(satellite, index=False)
    audit = audit_csv(satellite, "timestamp")
    assert audit["missing_hours"] == 1 and audit["nonfinite_numeric_cells"]["B08_mean_K"] == 1
    built, _ = build_dataset([satellite], [weather], {})
    samples = make_sequences(built)
    assert samples.rejected["gapped_window"] > 0 and samples.rejected["invalid_features"] > 0
    missing = pd.Timestamp("2024-01-01T12:00:00Z")
    assert all(not (start <= missing <= target) for start, target in zip(samples.input_starts, samples.targets))
    frame.iloc[0, frame.columns.get_loc("timestamp")] = "2024-01-01T00:30:00Z"
    frame.to_csv(satellite, index=False)
    with pytest.raises(ValueError, match="Off-hour"):
        build_dataset([satellite], [weather], {})


def test_target_tampering_and_invalid_weather(sample_data):
    frame, _, samples = sample_data
    modified = frame.copy()
    modified.loc[7, "target_heat_index_1h_C"] += 1
    with pytest.raises(ValueError, match="aligned"):
        make_sequences(modified)
    assert np.isnan(heat_index_c([27,27], [-1,101])).all()
    assert np.isnan(heat_index_c([np.inf], [75])).all()


def test_chronological_splits_scaling_and_walk_forward(sample_data):
    _, _, samples = sample_data
    splits = chronological_split(samples.targets)
    train, validation, test = (splits[name] for name in ("train", "validation", "test"))
    assert samples.targets[train[-1]] < samples.targets[validation[0]] < samples.targets[test[0]]
    assert samples.targets[train[-1]] <= samples.origins[validation[0]]
    scaler = Scaling.fit(samples.x[train], samples.y[train])
    np.testing.assert_allclose(scaler.x_mean, samples.x[train].reshape(-1,7).mean(axis=0))
    changed = deepcopy(samples)
    changed.x[test] += 10000; changed.y[test] += 10000
    assert scaler == Scaling.fit(changed.x[train], changed.y[train])
    assert not sufficiency(samples, splits, load_config()["minimum"])["screening_passed"]
    development = samples.targets[:test[0]]
    folds = list(walk_forward_splits(development, 30, 10, 10, 10))
    assert folds and max(folds[-1]["test"]) < test[0]
    for fold in folds:
        assert max(fold["train"]) < min(fold["validation"]) <= max(fold["validation"]) < min(fold["test"])
    with pytest.raises(ValueError):
        chronological_split(samples.targets[:2])
    with pytest.raises(ValueError):
        list(walk_forward_splits(samples.targets, 10, 10, 10, 1))
