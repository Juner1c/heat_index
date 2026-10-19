from __future__ import annotations

import argparse
from pathlib import Path
import random

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from backend.main import observations
from ml.model import HeatIndexLNN, save_artifact


def sequences(values: np.ndarray, target_index: int, length: int) -> tuple[np.ndarray, np.ndarray]:
    inputs, targets = [], []
    for end in range(length, len(values)):
        inputs.append(values[end-length:end])
        targets.append(values[end, target_index])
    return np.asarray(inputs, dtype=np.float32), np.asarray(targets, dtype=np.float32)


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = actual - predicted
    return {"mae_c": float(np.mean(np.abs(error))), "rmse_c": float(np.sqrt(np.mean(error**2)))}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a Liquid Time-Constant heat-index model.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sequence-length", type=int, default=24)
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)

    raw = pd.read_csv(args.csv)
    frame, _ = observations(raw)
    feature_columns = [column for column in frame.columns if column != "timestamp"]
    if "heat_index_c" not in feature_columns:
        raise SystemExit("Training requires heat_index_c or derivable temperature and humidity.")
    frame = frame[["timestamp", *feature_columns]].dropna().sort_values("timestamp")
    if len(frame) <= args.sequence_length + 10:
        raise SystemExit(f"Need more than {args.sequence_length + 10} complete rows; found {len(frame)}.")

    values = frame[feature_columns].to_numpy(dtype=np.float32)
    target_index = feature_columns.index("heat_index_c")
    sample_count = len(values) - args.sequence_length
    train_samples = max(1, int(sample_count * 0.70))
    validation_samples = max(1, int(sample_count * 0.15))
    train_row_end = args.sequence_length + train_samples
    feature_mean = values[:train_row_end].mean(axis=0)
    feature_scale = values[:train_row_end].std(axis=0)
    feature_scale[feature_scale == 0] = 1
    target_mean = float(values[:train_row_end, target_index].mean())
    target_scale = float(values[:train_row_end, target_index].std()) or 1.0
    normalized = (values - feature_mean) / feature_scale
    inputs, targets = sequences(normalized, target_index, args.sequence_length)

    train_x, train_y = inputs[:train_samples], targets[:train_samples]
    validation_end = min(train_samples + validation_samples, sample_count - 1)
    validation_x, validation_y = inputs[train_samples:validation_end], targets[train_samples:validation_end]
    test_x, test_y = inputs[validation_end:], targets[validation_end:]
    model = HeatIndexLNN(len(feature_columns), args.hidden_size)
    optimizer, loss_fn = torch.optim.Adam(model.parameters(), lr=args.learning_rate), nn.MSELoss()
    loader = DataLoader(TensorDataset(torch.from_numpy(train_x), torch.from_numpy(train_y)), batch_size=args.batch_size, shuffle=False)
    best_state, best_loss = None, float("inf")
    for _ in range(args.epochs):
        model.train()
        for batch_x, batch_y in loader:
            optimizer.zero_grad(); loss = loss_fn(model(batch_x), batch_y); loss.backward(); optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = loss_fn(model(torch.from_numpy(validation_x)), torch.from_numpy(validation_y)).item()
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
    model.load_state_dict(best_state)

    split_metrics = {}
    model.eval()
    with torch.no_grad():
        for name, split_x, split_y in (("train", train_x, train_y), ("validation", validation_x, validation_y), ("test", test_x, test_y)):
            predicted = model(torch.from_numpy(split_x)).numpy() * target_scale + target_mean
            actual = split_y * target_scale + target_mean
            split_metrics[name] = {"samples": len(actual), **metrics(actual, predicted)}
    metadata = {
        "model_type": "liquid_time_constant", "feature_columns": feature_columns,
        "sequence_length": args.sequence_length, "hidden_size": args.hidden_size,
        "feature_mean": feature_mean.tolist(), "feature_scale": feature_scale.tolist(),
        "target_mean": target_mean, "target_scale": target_scale,
        "split_policy": "chronological_70_15_15", "metrics": split_metrics,
        "training_rows": len(frame), "data_start": frame.iloc[0]["timestamp"].isoformat(),
        "data_end": frame.iloc[-1]["timestamp"].isoformat(), "seed": args.seed,
    }
    save_artifact(args.output, model, metadata)
    print(f"Saved LNN artifact to {args.output}")
    print(split_metrics)


if __name__ == "__main__":
    main()
