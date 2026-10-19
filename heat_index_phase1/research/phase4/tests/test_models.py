from copy import deepcopy

import numpy as np
import pytest
import torch

from research.phase4.common import FEATURES, dependency_versions, load_config
from research.phase4.data.temporal_split import chronological_split, split_metadata
from research.phase4.models.artifacts import create_model, load_checkpoint, predict_checkpoint, save_checkpoint
from research.phase4.models.persistence import predict as persistence
from research.phase4.training.evaluate import grouped_errors, metrics, prediction_records
from research.phase4.training.train import train_model
from research.phase4.tests.test_data import local_sources, sample_data


@pytest.mark.parametrize("identifier", ["mlp", "ltc", "cfc"])
def test_shapes_canonical_classes_training_smoke_reload_and_reproducibility(identifier, sample_data, tmp_path):
    _, manifest, samples = sample_data
    config = load_config(); config.update(epochs=2, patience=2, hidden_size=4, batch_size=64)
    splits = chronological_split(samples.targets)
    model, scaler, history, details = train_model(identifier, samples, splits, config)
    assert model(torch.zeros(2,6,7)).shape == (2,)
    if identifier == "ltc":
        from ncps.torch import LTC
        assert isinstance(model.recurrent, LTC)
    if identifier == "cfc":
        from ncps.torch import CfC
        assert isinstance(model.recurrent, CfC)
    # Altering only final-test values cannot change learned weights, scalers, or selected epoch.
    changed = deepcopy(samples); changed.x[splits["test"]] += 10000; changed.y[splits["test"]] += 10000
    repeated, repeated_scaler, repeated_history, _ = train_model(identifier, changed, splits, config)
    assert scaler == repeated_scaler and history == repeated_history
    for key, value in model.state_dict().items():
        torch.testing.assert_close(value, repeated.state_dict()[key], rtol=0, atol=0)
    metadata = {"model": identifier, "architecture": type(model).__name__, "features": FEATURES, "sequence_length":6,
                "forecast_horizon_hours":1, "training_config":config, "scaling":scaler.to_dict(),
                "dataset_fingerprint":manifest["dataset_fingerprint"], "splits":split_metadata(samples,splits),
                "dependency_versions":dependency_versions(), "training_result": details}
    directory = tmp_path/identifier
    save_checkpoint(directory, model, metadata)
    loaded, _, _ = load_checkpoint(directory)
    values = samples.x[splits["test"]]
    with torch.inference_mode():
        expected = scaler.inverse_y(model(torch.from_numpy(scaler.transform_x(values))).numpy())
    np.testing.assert_allclose(predict_checkpoint(directory, values), expected, rtol=0, atol=0)
    np.testing.assert_array_equal(predict_checkpoint(directory, values), predict_checkpoint(directory, values))
    with pytest.raises(FileExistsError):
        save_checkpoint(directory, model, metadata)
    with pytest.raises(ValueError):
        predict_checkpoint(directory, values[:,:5])
    weights = directory/"weights.pt"
    weights.write_bytes(weights.read_bytes()+b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        load_checkpoint(directory)


def test_persistence_metrics_and_grouped_errors(sample_data):
    _, _, samples = sample_data
    np.testing.assert_array_equal(persistence(samples.persistence), samples.persistence)
    value = metrics([1,2,3], [2,3,4])
    assert value["mae_c"] == value["rmse_c"] == value["mean_bias_c"] == 1
    assert value["r2"] == -.5
    assert metrics([1], [1])["r2"] is None
    with pytest.raises(ValueError):
        metrics([1,2], [1])
    with pytest.raises(ValueError):
        persistence([np.nan])
    records = prediction_records(samples, np.arange(10), {"persistence": samples.persistence[:10]})
    assert len(grouped_errors(records, "hour_utc")) > 0
    assert grouped_errors(records, "heat_index_range_c").samples.sum() == 10


def test_invalid_config_and_small_data_gate(sample_data, tmp_path):
    from research.phase4.run import execute
    frame, manifest, samples = sample_data
    config = load_config(); splits = chronological_split(samples.targets)
    output = tmp_path/"blocked_experiment"
    with pytest.raises(ValueError, match="insufficient"):
        execute(config, smoke=False, root=output, prepared=(frame,manifest,samples,splits,{}))
    assert not output.exists()
    with pytest.raises(ValueError):
        create_model("single_time_constant",config)


def test_complete_experiment_artifacts_and_perfect_baseline_serialization(sample_data, tmp_path):
    """End-to-end engineering fixture; its artificial baseline is not scientific evidence."""
    import json
    from research.phase4.run import execute
    frame, manifest, samples = deepcopy(sample_data)
    config = load_config(); config.update(models=["mlp"], epochs=1, hidden_size=4)
    splits = chronological_split(samples.targets)
    samples.persistence = samples.y.copy()  # exercise undefined relative skill when baseline MAE is zero
    output = execute(config, smoke=True, root=tmp_path/"experiments", prepared=(frame,manifest,samples,splits,{}), historical_references=False)
    assert json.loads((output/"run_status.json").read_text())["status"] == "completed"
    results = json.loads((output/"reports"/"results.json").read_text())
    assert not results["promotion_eligible"]
    assert all(value["mae_skill_vs_persistence"] is None for value in results["comparison"])
    assert len(list((output/"figures").glob("*.png"))) == 4
    assert (output/"reports"/"model_comparison.md").is_file()
    assert (output/"predictions"/"predicted_vs_actual.csv").is_file()
    assert len(predict_checkpoint(output/"checkpoints"/"mlp", samples.x[splits["test"]])) == len(splits["test"])
