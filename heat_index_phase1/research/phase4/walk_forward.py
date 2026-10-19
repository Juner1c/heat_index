"""Optional expanding-window research, restricted to the development partition."""
import argparse
from pathlib import Path

from research.phase4.common import CONFIG_PATH, load_config, write_json
from research.phase4.data.temporal_split import walk_forward_splits
from research.phase4.run import audit, execute, new_run_directory


def main():
    parser = argparse.ArgumentParser(description="Separate development-only walk-forward evaluation; final holdout is excluded.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    prepared = audit(config)
    samples, final_splits = prepared[2], prepared[3]
    development_count = int(final_splits["test"][0])
    targets = samples.targets[:development_count]
    size = max(1, int(development_count*.15))
    folds = list(walk_forward_splits(targets, int(development_count*.60), size, size, size))
    if not folds:
        raise ValueError("Insufficient development samples for walk-forward evaluation.")
    output = new_run_directory("walk_forward")
    runs = []
    for fold in folds:
        runs.append(str(execute(config, smoke=args.smoke, root=output, prepared=prepared, splits_override=fold, historical_references=False)))
    write_json(output/"walk_forward_manifest.json", {"folds": runs, "final_test_excluded": True,
                                                    "final_test_start": samples.targets[development_count].isoformat(), "promotion_eligible": False})
    print(output)


if __name__ == "__main__":
    main()
