
import copy
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

# ==================================================
# CONFIGURATION
# ==================================================
DATA_FILE = Path("heat_index_dataset.csv")
OUTPUT_DIR = Path("lnn_results")
OUTPUT_DIR.mkdir(exist_ok=True)

SEED = 42
TRAIN_RATIO = 0.80
EPOCHS = 250
LEARNING_RATE = 0.005
HIDDEN_SIZE = 24

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

DEVICE = torch.device("cpu")

# ==================================================
# LOAD DATA
# ==================================================
df = pd.read_csv(DATA_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

features = [
    "temperature_C",
    "humidity_percent",
    "dew_point_C",
    "B08_mean_K",
    "B13_mean_K",
    "B14_mean_K",
    "B15_mean_K",
]

required = [
    "timestamp",
    "heat_index_C",
    "target_heat_index_1h_C",
] + features

missing = [column for column in required if column not in df.columns]
if missing:
    raise ValueError(f"Missing required columns: {missing}")

df = df.sort_values("timestamp").reset_index(drop=True)

# Verify each row has a valid target one hour ahead.
# Only retain timestamps whose next original record is exactly one hour later.
next_time = df["timestamp"].shift(-1)
consecutive = (
    (next_time - df["timestamp"]) == pd.Timedelta(hours=1)
)

df = df.loc[consecutive].copy()

# Remove incomplete or non-numeric rows
for column in features + [
    "heat_index_C",
    "target_heat_index_1h_C",
]:
    df[column] = pd.to_numeric(df[column], errors="coerce")

df = df.dropna(
    subset=features + ["heat_index_C", "target_heat_index_1h_C"]
).reset_index(drop=True)

if len(df) < 20:
    raise ValueError(
        f"Only {len(df)} valid rows remain. "
        "More data is needed for this prototype."
    )

# ==================================================
# CHRONOLOGICAL TRAIN / TEST SPLIT
# ==================================================
split_index = int(len(df) * TRAIN_RATIO)

train_df = df.iloc[:split_index].copy()
test_df = df.iloc[split_index:].copy()

if len(test_df) == 0:
    raise ValueError("The test set is empty.")

# Fit scalers using training data only
x_scaler = StandardScaler()
y_scaler = StandardScaler()

X_train = x_scaler.fit_transform(train_df[features])
X_test = x_scaler.transform(test_df[features])

y_train = y_scaler.fit_transform(
    train_df[["target_heat_index_1h_C"]]
)

X_train_t = torch.tensor(X_train, dtype=torch.float32)
y_train_t = torch.tensor(y_train, dtype=torch.float32)
X_test_t = torch.tensor(X_test, dtype=torch.float32)

# ==================================================
# LIQUID NEURAL NETWORK
# ==================================================
class LiquidCell(nn.Module):
    def __init__(self, input_size, hidden_size):
        super().__init__()

        self.input_layer = nn.Linear(input_size, hidden_size)
        self.recurrent_layer = nn.Linear(hidden_size, hidden_size)
        self.tau = nn.Parameter(torch.ones(hidden_size))

    def forward(self, x, hidden):
        tau = torch.nn.functional.softplus(self.tau) + 0.1

        candidate = torch.tanh(
            self.input_layer(x)
            + self.recurrent_layer(hidden)
        )

        # Continuous-time-inspired state update
        dt = 1.0
        alpha = 1.0 - torch.exp(-dt / tau)

        return hidden + alpha * (candidate - hidden)


class LiquidNeuralNetwork(nn.Module):
    def __init__(self, input_size, hidden_size):
        super().__init__()

        self.hidden_size = hidden_size
        self.cell = LiquidCell(input_size, hidden_size)

        self.output_layer = nn.Sequential(
            nn.Linear(hidden_size, 16),
            nn.Tanh(),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        hidden = torch.zeros(
            x.shape[0],
            self.hidden_size,
            dtype=x.dtype,
            device=x.device,
        )

        hidden = self.cell(x, hidden)
        return self.output_layer(hidden)


model = LiquidNeuralNetwork(
    input_size=len(features),
    hidden_size=HIDDEN_SIZE,
).to(DEVICE)

optimizer = torch.optim.Adam(
    model.parameters(),
    lr=LEARNING_RATE,
)

loss_function = nn.MSELoss()

# ==================================================
# TRAIN
# ==================================================
print("=" * 55)
print("LIQUID NEURAL NETWORK - HEAT INDEX FORECAST")
print("=" * 55)
print(f"Device: {DEVICE}")
print(f"Valid hourly samples: {len(df)}")
print(f"Training samples: {len(train_df)}")
print(f"Testing samples: {len(test_df)}")
print(f"Input features: {features}")
print()

best_loss = float("inf")
best_state = None

for epoch in range(EPOCHS):
    model.train()
    optimizer.zero_grad()

    predictions = model(X_train_t)
    loss = loss_function(predictions, y_train_t)

    loss.backward()
    torch.nn.utils.clip_grad_norm_(
        model.parameters(),
        max_norm=1.0,
    )
    optimizer.step()

    current_loss = loss.item()

    if current_loss < best_loss:
        best_loss = current_loss
        best_state = copy.deepcopy(model.state_dict())

    if (epoch + 1) % 25 == 0:
        print(
            f"Epoch {epoch + 1:3d}/{EPOCHS} "
            f"| Training MSE: {current_loss:.5f}"
        )

if best_state is not None:
    model.load_state_dict(best_state)

# ==================================================
# EVALUATE
# ==================================================
model.eval()

with torch.no_grad():
    pred_scaled = model(X_test_t).cpu().numpy()

predicted_C = y_scaler.inverse_transform(
    pred_scaled
).ravel()

actual_C = test_df["target_heat_index_1h_C"].to_numpy()

mae = mean_absolute_error(actual_C, predicted_C)
rmse = np.sqrt(mean_squared_error(actual_C, predicted_C))

# Persistence baseline: use current Heat Index as forecast
baseline_C = test_df["heat_index_C"].to_numpy()

baseline_mae = mean_absolute_error(actual_C, baseline_C)
baseline_rmse = np.sqrt(
    mean_squared_error(actual_C, baseline_C)
)

print()
print("=" * 55)
print("HELD-OUT TEST RESULTS")
print(f"LNN MAE:       {mae:.3f} °C")
print(f"LNN RMSE:      {rmse:.3f} °C")
print()
print("PERSISTENCE BASELINE")
print(f"Baseline MAE:  {baseline_mae:.3f} °C")
print(f"Baseline RMSE: {baseline_rmse:.3f} °C")

# ==================================================
# SAVE RESULTS AND MODEL
# ==================================================
results = pd.DataFrame({
    "timestamp": test_df["timestamp"].to_numpy(),
    "actual_heat_index_1h_C": actual_C,
    "predicted_heat_index_1h_C": predicted_C,
    "baseline_heat_index_1h_C": baseline_C,
})

results["absolute_error_C"] = np.abs(
    results["actual_heat_index_1h_C"]
    - results["predicted_heat_index_1h_C"]
)

results.to_csv(
    OUTPUT_DIR / "test_predictions.csv",
    index=False,
)

torch.save(
    {
        "model_state_dict": model.state_dict(),
        "features": features,
        "hidden_size": HIDDEN_SIZE,
        "x_scaler_mean": x_scaler.mean_.tolist(),
        "x_scaler_scale": x_scaler.scale_.tolist(),
        "y_scaler_mean": y_scaler.mean_.tolist(),
        "y_scaler_scale": y_scaler.scale_.tolist(),
    },
    OUTPUT_DIR / "lnn_heat_index_model.pth",
)

print()
print("Saved files:")
print(OUTPUT_DIR / "test_predictions.csv")
print(OUTPUT_DIR / "lnn_heat_index_model.pth")
print()
print(
    "Training complete. Results are preliminary because "
    "the satellite dataset is small."
)