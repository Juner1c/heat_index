# ThermoCast Phase 4 — offline research

This package never imports the original training scripts, rewrites original data/checkpoints, downloads data, or promotes a model into the application.

From `ThermoCast\heat_index_phase1` in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-phase4.txt
python -m research.phase4.run --audit-only
python -m research.phase4.run --smoke
python -m pytest -q research/phase4/tests
```

Create the environment first with `python -m venv .venv` if necessary. No dependency installation was needed for the reported run. Outputs use unique run IDs under `experiments/phase4/`, with separate checkpoint, metric, prediction, figure, and report directories. A failed run is labeled failed, never validated.

Current data support only a smoke test: 244 six-hour examples, split into 170 training / 36 validation / 38 test targets. `run` without `--smoke` rejects the insufficient/previously inspected holdout. Do not relabel current smoke-test results as scientific validation.

Edit a separate copy of `config/experiment.yaml` for new local CSVs, provenance, sequence length, and registered experiments. Lists of source files support expansion; overlapping timestamps require explicit resolution. Source files remain unchanged. Specify an alternative config with `--config PATH` and an alternative source directory with `THERMOCAST_DATA_DIR`.

Optional development-only walk-forward command (implemented, not executed for the published smoke comparison):

```powershell
python -m research.phase4.walk_forward --smoke
```

Each fold refits scaling/weights on its own training history and excludes the reserved final test partition. No hyperparameters are automatically searched. Scientific model-promotion decisions still require new holdouts and explicit approval.

Reports:

- [Dataset audit](../../docs/PHASE4_DATASET_AUDIT.md)
- [Research method and citations](../../docs/PHASE4_RESEARCH_METHOD.md)
- [Model comparison](../../docs/PHASE4_MODEL_COMPARISON.md)
- [Completion report](../../docs/PHASE4_RESULTS.md)
