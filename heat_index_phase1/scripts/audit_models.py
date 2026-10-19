"""Read-only model audit: python -m scripts.audit_models. No training is executed."""
import json

import numpy as np

from backend.services.model_loader import MODEL_FILES, load_model
from backend.services.model_audit import comparison, replay
from backend.services.model_training_audit import training_audit
from backend.services.preprocessing import source_frame


def heat_index_check():
    frame = source_frame()
    t = frame["temperature_C"] * 9 / 5 + 32
    rh = frame["humidity_percent"].clip(0, 100)
    simple = (0.5 * (t + 61 + (t - 68) * 1.2 + rh * .094) + t) / 2
    regression = (-42.379 + 2.04901523*t + 10.14333127*rh - .22475541*t*rh - .00683783*t**2 - .05481717*rh**2 + .00122874*t**2*rh + .00085282*t*rh**2 - .00000199*t**2*rh**2)
    valid = simple >= 80
    heat = regression.where(valid, simple)
    low = valid & (rh < 13) & t.between(80, 112)
    heat -= (((13-rh)/4) * np.sqrt(np.maximum((17-abs(t-95))/17, 0))).where(low, 0)
    high = valid & (rh > 85) & t.between(80, 87)
    heat += (((rh-85)/10) * ((87-t)/5)).where(high, 0)
    error = np.abs((heat-32)*5/9 - frame["heat_index_C"])
    return {"rows": len(frame), "max_abs_difference_c": float(error.max()), "matches_existing_calculation": bool((error < 1e-8).all())}


def main():
    reports = {}
    for identifier in MODEL_FILES:
        loaded = load_model(identifier)
        audit = replay(identifier)
        reports[identifier] = {"metadata": loaded.metadata, "parameter_count": sum(parameter.numel() for parameter in loaded.model.parameters()),
                               "training": training_audit(identifier), "replay": {key: value for key, value in audit.items() if key != "records"}}
    print(json.dumps({"models": reports, "common_test_period": comparison(), "heat_index_calculation": heat_index_check()}, indent=2))


if __name__ == "__main__":
    main()
