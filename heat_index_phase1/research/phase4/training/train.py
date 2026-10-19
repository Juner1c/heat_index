from __future__ import annotations

import random
import time

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from research.phase4.models.artifacts import create_model
from research.phase4.training.scaling import Scaling


def seed_everything(seed: int, threads: int = 1):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)


def select_device(requested: str) -> torch.device:
    if requested not in {"cpu", "cuda", "auto"}:
        raise ValueError("Device must be cpu, cuda, or auto.")
    if requested == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA was requested but is unavailable; use CPU.")
    return torch.device("cuda" if requested != "cpu" and torch.cuda.is_available() else "cpu")


def train_model(identifier: str, samples, splits: dict, config: dict):
    """Test values are deliberately never indexed by this function."""
    seed_everything(config["seed"], config["threads"])
    device = select_device(config["device"])
    train_ids, validation_ids = splits["train"], splits["validation"]
    scaler = Scaling.fit(samples.x[train_ids], samples.y[train_ids])
    train_x, train_y = torch.from_numpy(scaler.transform_x(samples.x[train_ids])), torch.from_numpy(scaler.transform_y(samples.y[train_ids]))
    validation_x = torch.from_numpy(scaler.transform_x(samples.x[validation_ids])).to(device)
    validation_y = torch.from_numpy(scaler.transform_y(samples.y[validation_ids])).to(device)
    generator = torch.Generator().manual_seed(config["seed"])
    batches = DataLoader(TensorDataset(train_x, train_y), batch_size=config["batch_size"], shuffle=True, generator=generator, num_workers=0)
    model = create_model(identifier, config).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config["learning_rate"])
    loss_function = nn.MSELoss()
    history, best_loss, best_state, wait, best_epoch = [], float("inf"), None, 0, 0
    started = time.perf_counter()
    for epoch in range(1, config["epochs"]+1):
        model.train(); train_loss = 0.0
        for features, targets in batches:
            features, targets = features.to(device), targets.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_function(model(features), targets)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss; experiment aborted.")
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), config["gradient_clip"], error_if_nonfinite=True)
            optimizer.step()
            train_loss += loss.item()*len(features)
        model.eval()
        with torch.inference_mode():
            validation_loss = loss_function(model(validation_x), validation_y).item()
        if not np.isfinite(validation_loss):
            raise ValueError("Nonfinite validation loss; experiment aborted.")
        history.append({"epoch": epoch, "train_mse_scaled": train_loss/len(train_ids), "validation_mse_scaled": validation_loss})
        # Always preserve the actual lowest validation loss. min_delta controls patience only.
        improved = validation_loss < best_loss-config["min_delta"]
        if validation_loss < best_loss:
            best_loss, best_epoch = validation_loss, epoch
            best_state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
        wait = 0 if improved else wait+1
        if wait >= config["patience"]:
            break
    if best_state is None:
        raise ValueError("No valid checkpoint was selected.")
    model = model.cpu()
    model.load_state_dict(best_state, strict=True); model.eval()
    return model, scaler, history, {"best_epoch": best_epoch, "epochs_executed": len(history),
                                   "best_validation_mse_scaled": best_loss, "duration_seconds": time.perf_counter()-started,
                                   "parameter_count": sum(p.numel() for p in model.parameters()), "device": str(device)}
