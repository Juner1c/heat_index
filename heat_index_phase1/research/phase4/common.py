from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import yaml

from backend.services.datasets import data_root
from backend.services.model_loader import FEATURES

APP_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).parent / "config" / "experiment.yaml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def dependency_versions() -> dict:
    return {name: importlib.metadata.version(name) for name in
            ("torch", "ncps", "numpy", "pandas", "matplotlib", "PyYAML")}


def load_config(path: Path = CONFIG_PATH) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config["forecast_horizon_hours"] != 1:
        raise ValueError("Phase 4 supports one-hour targets only.")
    if config["sequence_length"] < 1 or config["hidden_size"] < 1:
        raise ValueError("Sequence length and hidden size must be positive.")
    if not set(config["models"]).issubset({"mlp", "ltc", "cfc"}) or not config["models"]:
        raise ValueError("Only separate experimental MLP, LTC, and CfC models may be trained.")
    if len(set(config["models"])) != len(config["models"]):
        raise ValueError("Model identifiers must not be duplicated.")
    for name in ("epochs", "patience", "batch_size", "threads"):
        if config[name] < 1:
            raise ValueError(f"{name} must be positive.")
    if config["learning_rate"] <= 0 or config["gradient_clip"] <= 0:
        raise ValueError("Learning rate and gradient clipping must be positive.")
    return config


def source_paths(config: dict) -> tuple[list[Path], list[Path]]:
    root = data_root()
    return ([root / path for path in config["data"]["satellite_csvs"]],
            [root / path for path in config["data"]["weather_csvs"]])
