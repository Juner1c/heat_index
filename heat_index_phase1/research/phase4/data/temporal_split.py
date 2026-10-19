from __future__ import annotations

import numpy as np
import pandas as pd


def chronological_split(targets: pd.DatetimeIndex, train_fraction=.70, validation_fraction=.15) -> dict[str, np.ndarray]:
    if not (0 < train_fraction < 1 and 0 < validation_fraction < 1 and train_fraction+validation_fraction < 1):
        raise ValueError("Split fractions must leave nonempty train, validation, and test partitions.")
    if targets.has_duplicates or not targets.is_monotonic_increasing or targets.hasnans:
        raise ValueError("Targets must be valid, unique, and chronological.")
    a, b = int(len(targets)*train_fraction), int(len(targets)*validation_fraction)
    if min(a, b, len(targets)-a-b) < 1:
        raise ValueError("Insufficient samples for three chronological partitions.")
    return {"train": np.arange(a), "validation": np.arange(a, a+b), "test": np.arange(a+b, len(targets))}


def split_metadata(samples, splits: dict) -> dict:
    return {name: {"samples": len(ids), "target_start_utc": samples.targets[ids[0]].isoformat(),
                   "target_end_utc": samples.targets[ids[-1]].isoformat(),
                   "first_origin_utc": samples.origins[ids[0]].isoformat(),
                   "input_start_utc": samples.input_starts[ids[0]].isoformat()}
            for name, ids in splits.items()}


def sufficiency(samples, splits: dict, minimum: dict) -> dict:
    days = (samples.targets[-1]-samples.input_starts[0]).total_seconds()/86400
    reasons = [f"{name} has {len(ids)} samples; screening minimum is {minimum[name+'_samples']}"
               for name, ids in splits.items() if len(ids) < minimum[name+"_samples"]]
    if days < minimum["coverage_days"]:
        reasons.append(f"Coverage is {days:.2f} days; screening minimum is {minimum['coverage_days']}")
    return {"screening_passed": not reasons, "coverage_days": days, "reasons": reasons,
            "note": "Minimums are configurable research screening policy, not guarantees of statistical validity."}


def walk_forward_splits(targets: pd.DatetimeIndex, initial_train: int, validation_size: int, test_size: int, step: int):
    """Expanding train, separate validation, non-overlapping test blocks; no training by default."""
    if min(initial_train, validation_size, test_size, step) < 1 or step < test_size:
        raise ValueError("Positive sizes and non-overlapping walk-forward test blocks are required.")
    if targets.has_duplicates or not targets.is_monotonic_increasing:
        raise ValueError("Walk-forward targets must be unique and chronological.")
    for stop in range(initial_train, len(targets)-validation_size-test_size+1, step):
        yield {"train": np.arange(stop), "validation": np.arange(stop, stop+validation_size),
               "test": np.arange(stop+validation_size, stop+validation_size+test_size)}
