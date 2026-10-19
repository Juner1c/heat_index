from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error


# File paths
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "heat_index_dataset.csv"
OUTPUT_DIR = BASE_DIR / "feature_comparison_results"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Features for each experiment
weather_features = [
    "temperature_C",
    "humidity_percent",
    "dew_point_C",
]

satellite_features = [
    "B08_mean_K",
    "B13_mean_K",
    "B14_mean_K",
    "B15_mean_K",
]

target_column = "target_heat_index_1h_C"
current_hi_column = "heat_index_C"


def calculate_metrics(actual, predicted):
    return {
        "MAE_C": mean_absolute_error(actual, predicted),
        "RMSE_C": np.sqrt(mean_squared_error(actual, predicted)),
    }


def main():
    print("Loading dataset...")

    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATA_FILE}\n"
            "Make sure heat_index_dataset.csv is in this folder."
        )

    df = pd.read_csv(DATA_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)

    required_columns = (
        weather_features
        + satellite_features
        + [target_column, current_hi_column, "timestamp"]
    )

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    # Keep the same complete observations for both models.
    df = df.dropna(subset=required_columns).copy()
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=required_columns).reset_index(drop=True)

    if len(df) < 20:
        raise ValueError(
            f"Only {len(df)} usable rows remain. "
            "More valid observations are needed for this comparison."
        )

    # Chronological split: older records for training,
    # newer records for testing.
    split_index = int(len(df) * 0.80)

    train_df = df.iloc[:split_index].copy()
    test_df = df.iloc[split_index:].copy()

    y_train = train_df[target_column]
    y_test = test_df[target_column]

    feature_sets = {
        "Weather only": weather_features,
        "Weather + satellite": weather_features + satellite_features,
    }

    results = []
    prediction_output = pd.DataFrame({
        "timestamp": test_df["timestamp"].values,
        "actual_next_hour_HI_C": y_test.values,
        "persistence_prediction_C": test_df[current_hi_column].values,
    })

    # Persistence baseline
    baseline_metrics = calculate_metrics(
        y_test,
        test_df[current_hi_column],
    )

    results.append({
        "Model": "Persistence baseline",
        "Features": "Current heat index only",
        "Training_rows": len(train_df),
        "Test_rows": len(test_df),
        **baseline_metrics,
    })

    # Train and evaluate both Ridge regression models.
    for model_name, features in feature_sets.items():
        model = make_pipeline(
            StandardScaler(),
            Ridge(alpha=1.0),
        )

        model.fit(train_df[features], y_train)
        predictions = model.predict(test_df[features])

        metrics = calculate_metrics(y_test, predictions)

        results.append({
            "Model": model_name,
            "Features": ", ".join(features),
            "Training_rows": len(train_df),
            "Test_rows": len(test_df),
            **metrics,
        })

        column_name = (
            "weather_only_prediction_C"
            if model_name == "Weather only"
            else "weather_satellite_prediction_C"
        )

        prediction_output[column_name] = predictions

    # Save results
    metrics_df = pd.DataFrame(results)
    metrics_path = OUTPUT_DIR / "comparison_metrics.csv"
    predictions_path = OUTPUT_DIR / "comparison_predictions.csv"

    metrics_df.to_csv(metrics_path, index=False)
    prediction_output.to_csv(predictions_path, index=False)

    print("\n========== DATA SUMMARY ==========")
    print(f"Usable observations: {len(df)}")
    print(f"Training observations: {len(train_df)}")
    print(f"Testing observations: {len(test_df)}")
    print(f"Training period: {train_df['timestamp'].min()} to "
          f"{train_df['timestamp'].max()}")
    print(f"Testing period: {test_df['timestamp'].min()} to "
          f"{test_df['timestamp'].max()}")

    print("\n========== MODEL COMPARISON ==========")
    print(metrics_df[["Model", "MAE_C", "RMSE_C"]].to_string(index=False))

    print("\nResults saved:")
    print(metrics_path)
    print(predictions_path)


if __name__ == "__main__":
    main()