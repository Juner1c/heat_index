from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class Scaling:
    x_mean: list
    x_scale: list
    y_mean: float
    y_scale: float

    @classmethod
    def fit(cls, train_x, train_y):
        x, y = np.asarray(train_x, float), np.asarray(train_y, float)
        if x.ndim != 3 or x.shape[-1] != 7 or len(x) != len(y) or not len(x) or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Scalers require finite training-only windows and targets.")
        flattened = x.reshape(-1, x.shape[-1])
        scale = flattened.std(axis=0)
        result = cls(flattened.mean(axis=0).tolist(), np.where(scale > 0, scale, 1).tolist(),
                     float(y.mean()), float(y.std()) if y.std() > 0 else 1.0)
        return cls.from_dict(result.to_dict())

    @classmethod
    def from_dict(cls, value):
        result = cls(**value)
        if np.asarray(result.x_mean).shape != (7,) or np.asarray(result.x_scale).shape != (7,):
            raise ValueError("Invalid saved feature scaling dimensions.")
        if not np.isfinite([*result.x_mean, *result.x_scale, result.y_mean, result.y_scale]).all() or min(result.x_scale) <= 0 or result.y_scale <= 0:
            raise ValueError("Invalid saved scaling values.")
        return result

    def to_dict(self):
        return asdict(self)

    def transform_x(self, values):
        values = np.asarray(values, float)
        if values.shape[-1] != 7 or not np.isfinite(values).all():
            raise ValueError("Cannot scale incomplete or nonfinite inputs.")
        return ((values-np.asarray(self.x_mean))/np.asarray(self.x_scale)).astype(np.float32)

    def transform_y(self, values):
        return ((np.asarray(values, float)-self.y_mean)/self.y_scale).astype(np.float32)

    def inverse_y(self, values):
        return np.asarray(values, dtype=float)*self.y_scale+self.y_mean
