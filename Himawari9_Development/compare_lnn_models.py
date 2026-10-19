
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Input files
SINGLE_FILE = Path("lnn_results/test_predictions.csv")
SEQUENCE_FILE = Path("lnn_sequence_results/test_predictions.csv")

# Output directory
OUTPUT_DIR = Path("lnn_model_comparison")
OUTPUT_DIR.mkdir(exist_ok=True)

# Load predictions
single = pd.read_csv(SINGLE_FILE)
sequence = pd.read_csv(SEQUENCE_FILE)

# Normalize forecast timestamps
single["target_timestamp"] = (
    pd.to_datetime(single["timestamp"]) + pd.Timedelta(hours=1)
)
sequence["target_timestamp"] = pd.to_datetime(
    sequence["target_timestamp"]
)

# Align both models by the forecasted hour
comparison = pd.merge(
    single,
    sequence,
    on="target_timestamp",
    how="inner",
    suffixes=("_single", "_sequence"),
    validate="one_to_one",
)

comparison = comparison.sort_values(
    "target_timestamp"
).reset_index(drop=True)

if comparison.empty:
    raise ValueError(
        "No matching forecast timestamps. Check timestamp alignment."
    )

# Confirm that both models use the same actual heat index
actual_single = comparison["actual_heat_index_1h_C_single"]
actual_sequence = comparison["actual_heat_index_1h_C_sequence"]

if not np.allclose(
    actual_single,
    actual_sequence,
    atol=1e-5,
    rtol=0,
):
    raise ValueError(
        "Actual heat index values differ between prediction files."
    )

actual = actual_single.to_numpy()

# Calculate errors
def calculate_metrics(predictions):
    predictions = np.asarray(predictions, dtype=float)
    return {
        "MAE_C": mean_absolute_error(actual, predictions),
        "RMSE_C": np.sqrt(
            mean_squared_error(actual, predictions)
        ),
    }

models = {
    "Single LNN": comparison[
        "predicted_heat_index_1h_C_single"
    ],
    "Sequence LNN": comparison[
        "predicted_heat_index_1h_C_sequence"
    ],
    "Persistence baseline": comparison[
        "baseline_heat_index_1h_C_single"
    ],
}

# Check that persistence baselines agree
if not np.allclose(
    comparison["baseline_heat_index_1h_C_single"],
    comparison["baseline_heat_index_1h_C_sequence"],
    atol=1e-5,
    rtol=0,
):
    raise ValueError(
        "Persistence baselines differ between the two files."
    )

results = []

for name, predictions in models.items():
    metrics = calculate_metrics(predictions)
    results.append({
        "Model": name,
        "Test_samples": len(comparison),
        **metrics,
    })

metrics_df = pd.DataFrame(results)
metrics_df = metrics_df.sort_values("MAE_C")

# Save aligned predictions and metrics
comparison.to_csv(
    OUTPUT_DIR / "aligned_predictions.csv",
    index=False,
)
metrics_df.to_csv(
    OUTPUT_DIR / "model_metrics.csv",
    index=False,
)

print("=" * 60)
print("FAIR LNN MODEL COMPARISON")
print("=" * 60)

print(f"Matched forecast timestamps: {len(comparison)}")
print(
    "Test period:",
    comparison["target_timestamp"].min(),
    "to",
    comparison["target_timestamp"].max(),
)

print("\nMODEL PERFORMANCE")
print(metrics_df.to_string(index=False, float_format="%.4f"))

print("\nResults saved in:", OUTPUT_DIR.resolve())
