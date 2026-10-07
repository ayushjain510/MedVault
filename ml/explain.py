"""Global SHAP feature-importance summaries for each trained model.

Per-patient (local) explanations are computed on demand by the backend;
this script precomputes global summaries for the model-monitoring page.
"""
import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
import shap

from features import feature_columns, humanize_feature
from train import TASKS, patient_split

DATA = Path(__file__).parent / "data"
MODELS = Path(__file__).parent / "models"


def get_estimator(bundle):
    m = bundle["model"]
    if hasattr(m, "named_steps"):
        return m.named_steps["clf"], m
    return m, None


def main():
    feats = pd.read_parquet(DATA / "features.parquet")
    patients = pd.read_csv(DATA / "patients.csv")
    fcols = feature_columns(feats)
    _, _, te_ids = patient_split(patients)
    Xte = feats.loc[feats["patient_id"].isin(te_ids), fcols]
    sample = Xte.sample(min(600, len(Xte)), random_state=0)

    out = {}
    for task in TASKS:
        with open(MODELS / f"{task}.pkl", "rb") as f:
            bundle = pickle.load(f)
        est, pipe = get_estimator(bundle)
        name = bundle["model_name"]

        if name == "logistic_regression":
            X = pipe.named_steps["sc"].transform(pipe.named_steps["imp"].transform(sample.values))
            coefs = est.coef_  # (n_classes_or_1, n_features)
            imp = np.mean(np.abs(coefs), axis=0) * np.std(X, axis=0)
        else:
            Xs = sample.values
            if pipe is not None:
                Xs = pipe.named_steps["imp"].transform(Xs)
            explainer = shap.TreeExplainer(est)
            sv = explainer.shap_values(Xs, check_additivity=False)
            if isinstance(sv, list):
                imp = np.mean([np.abs(s).mean(axis=0) for s in sv], axis=0)
            elif sv.ndim == 3:
                imp = np.abs(sv).mean(axis=(0, 2))
            else:
                imp = np.abs(sv).mean(axis=0)

        order = np.argsort(imp)[::-1][:20]
        out[task] = {
            "model": name,
            "top_features": [{"feature": fcols[i], "label": humanize_feature(fcols[i]),
                              "importance": round(float(imp[i]), 5)} for i in order],
        }
        print(f"{task} ({name}): top = {[fcols[i] for i in order[:5]]}")

    with open(MODELS / "global_importance.json", "w") as f:
        json.dump(out, f, indent=2)
    print("saved global_importance.json")


if __name__ == "__main__":
    main()
