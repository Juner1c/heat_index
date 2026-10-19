# Original model audit — October 14, 2026

## Architecture and classification

The original checkpoints were reconstructed from the inspected class definitions in `Himawari9_Development/train_lnn.py` and `train_lnn_sequence.py`. Neither training script was imported or executed. Tests compile only their class definitions to compare the reconstructed architecture against the original forward pass.

Both models contain 1,233 parameters:

```text
7 input features
  → custom LiquidCell, 24 hidden units
  → Linear(24, 16) → Tanh → Linear(16, 1)

tau = softplus(learned_tau) + 0.1
candidate = tanh(W_input x + b_input + W_recurrent h + b_recurrent)
alpha = 1 - exp(-1 / tau)
h_next = h + alpha * (candidate - h)
```

These are **custom time-constant RNNs inspired by continuous-time dynamics**. Their trained per-unit time constants are fixed during inference; they are not input/state-dependent liquid time constants. They should not be described as implementations of canonical Liquid Time-Constant networks or CfC. The [original LTC paper](https://arxiv.org/abs/2006.04439) describes liquid time constants coupled to hidden state and numerical differential-equation solvers.

The single-observation implementation initializes hidden state to zero and applies the cell once per row. It does not preserve temporal state between samples. The sequence implementation starts from zero and applies the same cell to six consecutive hourly observations. Changing either architecture to `ncps.torch.LTC`, CfC, LSTM, or the earlier experimental `ml/model.py` would be incompatible with these original checkpoints.

## Features, units, and preprocessing

The exact input order is:

1. `temperature_C` — ground-weather air temperature, °C
2. `humidity_percent` — relative humidity, %
3. `dew_point_C` — dew point, °C
4. `B08_mean_K` — satellite brightness temperature, K
5. `B13_mean_K` — satellite brightness temperature, K
6. `B14_mean_K` — satellite brightness temperature, K
7. `B15_mean_K` — satellite brightness temperature, K

The target is `target_heat_index_1h_C`, representing the heat index exactly one hour after the final input timestamp. The models support **one hour only**. Six input hours do not imply a six-hour forecast horizon.

Both checkpoints are dictionaries containing `model_state_dict`, `features`, `hidden_size`, `x_scaler_mean`, `x_scaler_scale`, `y_scaler_mean`, and `y_scaler_scale`. The sequence checkpoint also stores `sequence_length=6`.

Inference computes `(x - saved_input_mean) / saved_input_scale` in the original feature order, casts to float32 for PyTorch, then inversely transforms output using the saved output mean/scale. The sequence training code first casts windows to float32 and applies scaling in place; this convention is retained. No scaler is fitted or reconstructed from inference observations. The single and sequence scalers differ and must not be interchanged.

Independent training-statistic checks, without fitting any scaler, confirm that the saved means and population standard deviations match the original training-only samples: maximum difference below `1.8e-13` for single, zero for sequence. The sequence scaler was fitted to flattened overlapping training windows, so repeated observations receive their original weighting.

## Checkpoint compatibility

| API identifier | Original checkpoint | Input shape | Version SHA-256 prefix | Compatible |
| --- | --- | --- | --- | --- |
| `single_time_constant` | `lnn_results/lnn_heat_index_model.pth` | `[batch, 7]` | `5651ea14a422` | Yes |
| `sequence_time_constant` | `lnn_sequence_results/lnn_sequence_model.pth` | `[batch, 6, 7]` | `195c526299a8` | Yes |

Loading uses CPU `torch.load(..., weights_only=True)`, strict state-dictionary matching, finite-weight checks, and validated feature/scaler metadata. The original nine state-dictionary tensors match both reconstructed classes. Model evaluation mode and `torch.inference_mode()` are used. Inference dependencies are PyTorch, NumPy, and Pandas; scikit-learn and ncps are not needed for these original checkpoints.

Saved held-out predictions reproduce within `0.000007 °C`. The maximum audit tolerance is `0.00005 °C` to accommodate float32 arithmetic and library/platform differences. Reference-class and reconstructed-class forward passes are equal when given the same tensor. This establishes checkpoint compatibility, not prospective forecasting accuracy.

## Training and target alignment

| Property | Single observation | Six-hour sequence |
| --- | --- | --- |
| Valid supervised samples | 259 | 244 |
| Training / testing samples | 207 / 52 | 195 / 49 |
| Training target period, UTC | Aug 1 01:00–Aug 9 19:00, 2024 | Aug 1 06:00–Aug 9 22:00, 2024 |
| Test target period, UTC | Aug 9 20:00–Aug 11 23:00, 2024 | Aug 9 23:00–Aug 11 23:00, 2024 |
| Split | Chronological 80/20 | Chronological 80/20 |
| Epochs / Adam learning rate | 250 / 0.005 | 300 / 0.003 |
| Hidden size / seed | 24 / 42 | 24 / 42 |

Targets were independently checked against the next actual hourly heat-index row. Gaps are excluded during original supervised sample creation. Sequence samples require six consecutive observations plus a consecutive next-hour target. Saved single-model CSV timestamps denote the **input hour** and require +1 hour for comparison; sequence CSV timestamps already denote the **target hour**.

Both scalers were fitted on training data only. Neither training script defines an independent validation split; checkpoint selection uses training loss. The sequence train/test windows share some past context at the boundary. That is historical context available at the forecast origin, but it is not an independent validation set. Operational availability of the retrospective gridded weather data has not been established.

## Evaluation on a common period

Both models and persistence were aligned to the same 49 target hours: August 9, 2024 at 23:00 through August 11 at 23:00 UTC.

| Predictor | MAE, °C | RMSE, °C | Mean bias, °C |
| --- | ---: | ---: | ---: |
| Persistence | 0.941808 | 1.331892 | -0.125018 |
| Single time-constant model | 1.121703 | 1.415527 | +0.093784 |
| Sequence time-constant model | 1.278643 | 1.687439 | +0.229003 |

Bias is prediction minus actual. Persistence outperforms both trained models on this common test period. The single model's own 52-target test MAE/RMSE are 1.093953/1.385634 °C; those must not be directly compared with the sequence model's 49-target results without temporal alignment.

The heat-index source itself was independently recalculated from ground air temperature and humidity using the inspected preparation script's NWS preliminary/Rothfusz/humidity-adjustment method. All 262 stored values agree within `8e-15 °C`. Satellite brightness temperatures are input covariates, not replacements for air temperature or heat index.

## Limits and next work

The original data cover only eleven August 2024 days, with two missing hourly observations. Results are retrospective tests on model-derived weather, not prospective local station validation. Inference readiness does not establish model superiority, deployment readiness, calibrated uncertainty, or performance in other seasons. Additional chronological holdouts and prospective aligned observations are required. Architectural changes or retraining require explicit approval.

Reproduce the audit without training:

```powershell
python -m scripts.audit_models
```
