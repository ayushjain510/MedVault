"""Runtime prediction + local explanation service.

Loads serialized model bundles lazily to keep memory usage low on
resource-constrained deployments. Uses the exact same feature pipeline
(ml/features.py) used at training time.
"""

import sys
import json
import pickle
import gc
import numpy as np
import pandas as pd

from functools import lru_cache
from collections.abc import Mapping

from ..config import ML_DIR, MODELS_DIR

sys.path.insert(0, str(ML_DIR))
from features import build_features, feature_columns, humanize_feature  # noqa: E402


TASK_ORDER = [
    "sepsis_state",
    "deterioration_6h",
    "deterioration_12h",
    "deterioration_24h",
    "antibiotic_response",
    "fluid_status",
    "recovery",
]


def _load_single_bundle(task: str):
    """Load one model bundle only when it is needed."""

    with open(MODELS_DIR / f"{task}.pkl", "rb") as f:
        bundle = pickle.load(f)

    # Compatibility fix for models trained with an older
    # scikit-learn version.
    model = bundle["model"]

    if hasattr(model, "named_steps"):
        for step in model.named_steps.values():
            if hasattr(step, "statistics_") and not hasattr(step, "_fill_dtype"):
                step._fill_dtype = step.statistics_.dtype

    return bundle


class LazyBundles(Mapping):
    """Lazy model collection.

    Models are loaded one at a time instead of all being kept in RAM.
    """

    def __init__(self):
        self._keys = tuple(TASK_ORDER)

    def __getitem__(self, task):
        if task not in self._keys:
            raise KeyError(task)

        return _load_single_bundle(task)

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)

    def items(self):
        """Yield one model at a time to avoid holding all models in memory."""
        for task in self._keys:
            bundle = _load_single_bundle(task)
            yield task, bundle
            del bundle
            gc.collect()


@lru_cache(maxsize=1)
def load_bundles():
    """Return a lazy model collection instead of loading every model."""
    return LazyBundles()


@lru_cache(maxsize=1)
def load_report():
    with open(MODELS_DIR / "report.json") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_global_importance():
    with open(MODELS_DIR / "global_importance.json") as f:
        return json.load(f)


def compute_features_for_patient(
    vitals: pd.DataFrame,
    patient_row: dict,
    abx: pd.DataFrame,
) -> pd.DataFrame:
    pdf = pd.DataFrame([patient_row])
    return build_features(vitals, pdf, abx)


def predict_all(feat_row: pd.DataFrame) -> dict:
    """Predict all tasks while loading only one model at a time."""

    bundles = load_bundles()
    out = {}

    for task in TASK_ORDER:
        bundle = bundles[task]

        X = feat_row[bundle["feature_columns"]].values
        model = bundle["model"]

        proba = model.predict_proba(X)[0]
        cls = int(np.argmax(proba))

        model_classes = (
            list(model.classes_)
            if hasattr(model, "classes_")
            else list(range(len(proba)))
        )

        cls_label_idx = int(model_classes[cls])

        out[task] = {
            "predicted_class": cls_label_idx,
            "predicted_label": bundle["classes"][cls_label_idx],
            "probability": round(float(proba[cls]), 4),
            "probabilities": {
                bundle["classes"][int(model_classes[i])]: round(float(p), 4)
                for i, p in enumerate(proba)
            },
            "model": bundle["model_name"],
        }

        del bundle
        gc.collect()

    return out


def _local_contributions(
    bundle,
    X_row: np.ndarray,
    predicted_class_pos: int,
):
    """SHAP for tree models; coefficient*value for the logistic pipeline."""

    import shap

    model = bundle["model"]
    fcols = bundle["feature_columns"]

    if hasattr(model, "named_steps"):
        imp_ = model.named_steps["imp"]
        clf = model.named_steps["clf"]

        if "sc" in model.named_steps:
            Xs = model.named_steps["sc"].transform(
                imp_.transform(X_row.reshape(1, -1))
            )[0]

            coefs = clf.coef_

            row = (
                coefs[predicted_class_pos]
                if coefs.shape[0] > 1
                else coefs[0]
            )

            contrib = row * Xs

        else:
            Xs = imp_.transform(X_row.reshape(1, -1))

            explainer = shap.TreeExplainer(clf)

            sv = explainer.shap_values(
                Xs,
                check_additivity=False,
            )

            contrib = _pick_class(sv, predicted_class_pos)

    else:
        explainer = shap.TreeExplainer(model)

        sv = explainer.shap_values(
            X_row.reshape(1, -1),
            check_additivity=False,
        )

        contrib = _pick_class(sv, predicted_class_pos)

    return list(zip(fcols, contrib))


def _pick_class(sv, cls_pos):
    if isinstance(sv, list):
        arr = sv[cls_pos] if len(sv) > 1 else sv[0]
        return np.asarray(arr)[0]

    arr = np.asarray(sv)

    if arr.ndim == 3:
        return arr[0, :, cls_pos]

    return arr[0]


def explain_prediction(
    feat_row: pd.DataFrame,
    task: str,
    top_k: int = 8,
) -> dict:

    bundles = load_bundles()
    bundle = bundles[task]
    model = bundle["model"]

    X = feat_row[bundle["feature_columns"]].values[0]

    proba = model.predict_proba(
        X.reshape(1, -1)
    )[0]

    cls_pos = int(np.argmax(proba))

    model_classes = (
        list(model.classes_)
        if hasattr(model, "classes_")
        else list(range(len(proba)))
    )

    cls_label_idx = int(model_classes[cls_pos])

    pairs = _local_contributions(
        bundle,
        X,
        cls_pos,
    )

    pairs.sort(
        key=lambda t: -abs(t[1])
    )

    top = pairs[:top_k]

    fvals = {
        c: feat_row[c].values[0]
        for c, _ in top
    }

    result = {
        "task": task,
        "predicted_label": bundle["classes"][cls_label_idx],
        "probability": round(float(proba[cls_pos]), 4),
        "model": bundle["model_name"],
        "factors": [
            {
                "feature": c,
                "label": humanize_feature(c),
                "contribution": round(float(v), 4),
                "direction": "increases" if v > 0 else "decreases",
                "value": (
                    round(float(fvals[c]), 3)
                    if not pd.isna(fvals[c])
                    else None
                ),
            }
            for c, v in top
        ],
    }

    del bundle
    gc.collect()

    return result