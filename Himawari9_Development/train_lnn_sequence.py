
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
OUTPUT_DIR = Path("lnn_sequence_results")
OUTPUT_DIR.mkdir(exist_ok=True)

SEED = 42
TRAIN_RATIO = 0.80
SEQUENCE_LENGTH = 6
EPOCHS = 300
LEARNING_RATE = 0.003
HIDDEN_SIZE = 24

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

DEVICE = torch.device("cpu")

FEATURES = [
    "temperature_C",
    "humidity_percent",
    "dew_point_C",
    "B08_mean_K",
    "B13_mean_K",
    "B14_mean_K",
    "B15_mean_K",
]

# ==================================================
# LOAD DATA
# ==================================================
df = pd.read_csv(DATA_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.sort_values("timestamp").reset_index(drop=True)

required = FEATURES + [
    "timestamp",
    "heat_index_C",
    "target_heat_index_1h_C",
]

missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns: {missing}")

for column in FEATURES + [
    "heat_index_C",
    "target_heat_index_1h_C",
]:
    df[column] = pd.to_numeric(df[column], errors="coerce")

df = df.dropna(subset=["timestamp"]).reset_index(drop=True)

# Fit only on consecutive hourly sequences with complete values.
# A sample uses six input hours and predicts the target one hour
# after the final input hour.
feature_values = df[FEATURES].to_numpy(dtype=float)
heat_index_values = df["heat_index_C"].to_numpy(dtype=float)
target_values = df["target_heat_index_1h_C"].to_numpy(dtype=float)
timestamps = df["timestamp"].to_numpy()

sequences = []
targets = []
current_heat_index = []
target_timestamps = []

for end in range(SEQUENCE_LENGTH - 1, len(df)):
    start = end - SEQUENCE_LENGTH + 1

    # Six observations must be consecutive hourly records.
    sequence_times = pd.to_datetime(timestamps[start:end + 1])
    gaps = sequence_times.to_series().diff().dropna()

    if not (gaps == pd.Timedelta(hours=1)).all():
        continue

    # The target must correspond to the hour immediately after
    # the last input observation.
    if pd.isna(target_values[end]):
        continue

    next_time = pd.Timestamp(timestamps[end]) + pd.Timedelta(hours=1)
    actual_next_time = (
        pd.Timestamp(timestamps[end + 1])
        if end + 1 < len(df)
        else None
    )

    if actual_next_time is None or actual_next_time != next_time:
        continue

    sequence = feature_values[start:end + 1]

    if not np.isfinite(sequence).all():
        continue

    sequences.append(sequence)
    targets.append(target_values[end])
    current_heat_index.append(heat_index_values[end])
    target_timestamps.append(next_time)

X = np.asarray(sequences, dtype=np.float32)
y = np.asarray(targets, dtype=np.float32).reshape(-1, 1)
baseline = np.asarray(current_heat_index, dtype=np.float32)
target_timestamps = pd.to_datetime(target_timestamps)

if len(X) < 20:
    raise ValueError(
        f"Only {len(X)} valid sequences were created. "
        "More consecutive hourly satellite data is needed."
    )

# ==================================================
# CHRONOLOGICAL SPLIT
# ==================================================
split_index = int(len(X) * TRAIN_RATIO)

X_train_raw = X[:split_index]
X_test_raw = X[split_index:]
y_train_raw = y[:split_index]
y_test_raw = y[split_index:]

baseline_test = baseline[split_index:]
test_timestamps = target_timestamps[split_index:]

# Scale features using training data only.
x_scaler = StandardScaler()
x_scaler.fit(X_train_raw.reshape(-1, len(FEATURES)))

X_train = x_scaler.transform(
    X_train_raw.reshape(-1, len(FEATURES))
).reshape(X_train_raw.shape)

X_test = x_scaler.transform(
    X_test_raw.reshape(-1, len(FEATURES))
).reshape(X_test_raw.shape)

y_scaler = StandardScaler()
y_train = y_scaler.fit_transform(y_train_raw)
y_test = y_scaler.transform(y_test_raw)

X_train_t = torch.tensor(X_train, dtype=torch.float32)
y_train_t = torch.tensor(y_train, dtype=torch.float32)
X_test_t = torch.tensor(X_test, dtype=torch.float32)

# ==================================================
# SEQUENCE-BASED LIQUID NEURAL NETWORK
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

        # Continuous-time-inspired state update.
        dt = 1.0
        alpha = 1.0 - torch.exp(-dt / tau)

        return hidden + alpha * (candidate - hidden)


class SequenceLNN(nn.Module):
    def __init__(self, input_size, hidden_size):
        super().__init__()

        self.hidden_size = hidden_size
        self.cell = LiquidCell(input_size, hidden_size)
        self.output_layer = nn.Sequential(
            nn.Linear(hidden_size, 16),
            nn.Tanh(),
            nn.Linear(16, 1),
        )

    def forward(self, sequence):
        batch_size = sequence.shape[0]

        hidden = torch.zeros(
            batch_size,
            self.hidden_size,
            dtype=sequence.dtype,
            device=sequence.device,
        )

        # Process the six hourly observations in order.
        for step in range(sequence.shape[1]):
            hidden = self.cell(sequence[:, step, :], hidden)

        return self.output_layer(hidden)


model = SequenceLNN(
    input_size=len(FEATURES),
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
print("=" * 60)
print("SEQUENCE-BASED LIQUID NEURAL NETWORK")
print("=" * 60)
print(f"Device: {DEVICE}")
print(f"Sequence length: {SEQUENCE_LENGTH} hours")
print(f"Valid sequences: {len(X)}")
print(f"Training sequences: {len(X_train)}")
print(f"Testing sequences: {len(X_test)}")
print()

best_loss = float("inf")
best_state = None

for epoch in range(EPOCHS):
    model.train()
    optimizer.zero_grad()

    predictions = model(X_train_t)
    loss = loss_function(predictions, y_train_t)

    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
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
    predicted_scaled = model(X_test_t).cpu().numpy()

predicted_C = y_scaler.inverse_transform(
    predicted_scaled
).ravel()

actual_C = y_test_raw.ravel()

mae = mean_absolute_error(actual_C, predicted_C)
rmse = np.sqrt(mean_squared_error(actual_C, predicted_C))

baseline_mae = mean_absolute_error(actual_C, baseline_test)
baseline_rmse = np.sqrt(
    mean_squared_error(actual_C, baseline_test)
)

print()
print("=" * 60)
print("HELD-OUT TEST RESULTS")
print(f"Sequence LNN MAE:       {mae:.3f} °C")
print(f"Sequence LNN RMSE:      {rmse:.3f} °C")
print()
print("PERSISTENCE BASELINE")
print(f"Baseline MAE:           {baseline_mae:.3f} °C")
print(f"Baseline RMSE:          {baseline_rmse:.3f} °C")

# ==================================================
# SAVE RESULTS
# ==================================================
results = pd.DataFrame({
    "target_timestamp": test_timestamps,
    "actual_heat_index_1h_C": actual_C,
    "predicted_heat_index_1h_C": predicted_C,
    "baseline_heat_index_1h_C": baseline_test,
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
        "features": FEATURES,
        "sequence_length": SEQUENCE_LENGTH,
        "hidden_size": HIDDEN_SIZE,
        "x_scaler_mean": x_scaler.mean_.tolist(),
        "x_scaler_scale": x_scaler.scale_.tolist(),
        "y_scaler_mean": y_scaler.mean_.tolist(),
        "y_scaler_scale": y_scaler.scale_.tolist(),
    },
    OUTPUT_DIR / "lnn_sequence_model.pth",
)

print()
print("Saved files:")
print(OUTPUT_DIR / "test_predictions.csv")
print(OUTPUT_DIR / "lnn_sequence_model.pth")
print()
print(
    "Training complete. This is a prototype; evaluate it on "
    "more dates before drawing conclusions about generalization."
)