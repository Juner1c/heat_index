import numpy as np


def predict(last_observed_heat_index) -> np.ndarray:
    values = np.asarray(last_observed_heat_index, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Persistence requires finite, actually observed origin-time heat indices.")
    return values.copy()
