"""Model training & comparison for MedVault.

Compares Logistic Regression, Random Forest and XGBoost on each of the five
prediction tasks. Splits are PATIENT-LEVEL (no patient appears in more than
one split). Preprocessing (median imputation + scaling) is fitted on the
training set only. Class imbalance is handled via class weighting /
scale_pos_weight rather than resampling, avoiding leakage across timelines.

A temporal deep model (LSTM/GRU) was considered and deliberately not used:
with 240 patients the effective sample size at the patient level is small,
and gradient boosting over engineered temporal-window features is the
better-calibrated, more interpretable choice at this scale (see docs/methodology.md).
"""
import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                             roc_auc_score, average_precision_score, confusion_matrix,
                             brier_score_loss)
from sklearn.utils.class_weight import compute_sample_weight
import xgboost as xgb
import lightgbm as lgb
from sklearn.calibration import calibration_curve

from features import feature_columns

DATA = Path(__file__).parent / "data"
MODELS = Path(__file__).parent / "models"
SEED = 42

TASKS = {
    "sepsis_state": {"target": "state", "n_classes": 8,
                     "classes": ["Stable", "At Risk", "Active Sepsis", "Severe/Deteriorating",
                                 "Treatment Response", "Recovery", "Non-responding", "Escalation"]},
    "deterioration_6h": {"target": "y_det6", "n_classes": 2, "classes": ["No deterioration", "Deterioration ≤6h"]},
    "deterioration_12h": {"target": "y_det12", "n_classes": 2, "classes": ["No deterioration", "Deterioration ≤12h"]},
    "deterioration_24h": {"target": "y_det24", "n_classes": 2, "classes": ["No deterioration", "Deterioration ≤24h"]},
    "antibiotic_response": {"target": "y_abx", "n_classes": 5,
                            "classes": ["AR-0 Improving", "AR-1 Stable / no clear change", "AR-2 Uncertain",
                                        "AR-3 Poor response", "AR-4 Worsening"]},
    "fluid_status": {"target": "y_fluid", "n_classes": 6,
                     "classes": ["FS-0 Stable fluid trajectory", "FS-1 Monitor closely",
                                 "FS-2 Increasing positive balance", "FS-3 Significant accumulation concern",
                                 "FS-4 Possible inadequate hemodynamic response", "FS-5 Insufficient data"]},
    "recovery": {"target": "y_recovery", "n_classes": 6,
                 "classes": ["RT-0 Improving", "RT-1 Stable", "RT-2 Slow recovery",
                             "RT-3 Persistent concern", "RT-4 Worsening", "RT-5 Insufficient evidence"]},
}

MODEL_VERSION = "2.0"
FEATURE_VERSION = "1.1"


def patient_split(patients: pd.DataFrame, seed=SEED):
    """Stratified-by-archetype patient-level split: 70/15/15."""
    rng = np.random.default_rng(seed)
    train, val, test = [], [], []
    for _, g in patients.groupby("archetype"):
        ids = g["patient_id"].tolist()
        rng.shuffle(ids)
        n = len(ids)
        n_tr, n_va = int(n * 0.7), int(n * 0.15)
        train += ids[:n_tr]
        val += ids[n_tr:n_tr + n_va]
        test += ids[n_tr + n_va:]
    assert not (set(train) & set(val)) and not (set(train) & set(test)) and not (set(val) & set(test))
    return train, val, test


def make_models(n_classes: int, y_train: np.ndarray):
    lr = Pipeline([("imp", SimpleImputer(strategy="median")),
                   ("sc", StandardScaler()),
                   ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.1))])
    rf = Pipeline([("imp", SimpleImputer(strategy="median")),
                   ("clf", RandomForestClassifier(n_estimators=200, max_depth=12, min_samples_leaf=5,
                                                  class_weight="balanced", n_jobs=-1, random_state=SEED))])
    xgb_params = dict(n_estimators=300, max_depth=5, learning_rate=0.08, subsample=0.85,
                      colsample_bytree=0.7, reg_lambda=2.0, random_state=SEED,
                      tree_method="hist", n_jobs=-1, eval_metric="logloss")
    lgb_params = dict(n_estimators=300, max_depth=6, learning_rate=0.08, subsample=0.85,
                      colsample_bytree=0.7, reg_lambda=2.0, random_state=SEED,
                      class_weight="balanced", n_jobs=-1, verbose=-1)
    lg = lgb.LGBMClassifier(**lgb_params)
    if n_classes == 2:
        pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
        xg = xgb.XGBClassifier(**xgb_params, scale_pos_weight=pos_weight)
    else:
        xg = xgb.XGBClassifier(**xgb_params, objective="multi:softprob", num_class=n_classes)
    return {"logistic_regression": lr, "random_forest": rf, "xgboost": xg, "lightgbm": lg}


def evaluate(model, X, y, n_classes):
    pred = model.predict(X)
    proba = model.predict_proba(X)
    m = {
        "accuracy": accuracy_score(y, pred),
        "precision_macro": precision_score(y, pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y, pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y, pred, average="macro", zero_division=0),
        "f1_weighted": f1_score(y, pred, average="weighted", zero_division=0),
        "confusion_matrix": confusion_matrix(y, pred, labels=list(range(n_classes))).tolist(),
    }
    try:
        if n_classes == 2:
            m["roc_auc"] = roc_auc_score(y, proba[:, 1])
            m["pr_auc"] = average_precision_score(y, proba[:, 1])
            m["brier"] = brier_score_loss(y, proba[:, 1])
            m["sensitivity"] = recall_score(y, pred, pos_label=1, zero_division=0)
            tn = m["confusion_matrix"][0][0]
            fp = m["confusion_matrix"][0][1]
            m["specificity"] = tn / max(tn + fp, 1)
            frac_pos, mean_pred = calibration_curve(y, proba[:, 1], n_bins=10, strategy="quantile")
            m["calibration"] = {"mean_predicted": [round(float(v), 4) for v in mean_pred],
                                "fraction_positive": [round(float(v), 4) for v in frac_pos]}
        else:
            m["roc_auc"] = roc_auc_score(y, proba, multi_class="ovr", average="macro",
                                         labels=list(range(n_classes)))
    except ValueError:
        m["roc_auc"] = None
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}


def select_best(results: dict, task: str) -> str:
    """Prefer high recall on dangerous classes; use macro F1 + recall composite."""
    def score(r):
        rec = r["val"]["recall_macro"]
        f1 = r["val"]["f1_macro"]
        return 0.55 * rec + 0.45 * f1
    return max(results, key=lambda name: score(results[name]))


def main():
    feats = pd.read_parquet(DATA / "features.parquet")
    patients = pd.read_csv(DATA / "patients.csv")
    fcols = feature_columns(feats)

    tr_ids, va_ids, te_ids = patient_split(patients)
    splits = {"train": tr_ids, "val": va_ids, "test": te_ids}
    masks = {k: feats["patient_id"].isin(v) for k, v in splits.items()}
    print(f"split patients: train={len(tr_ids)} val={len(va_ids)} test={len(te_ids)}")

    MODELS.mkdir(exist_ok=True)
    report = {"tasks": {}, "feature_columns": fcols,
              "splits": {k: v for k, v in splits.items()},
              "trained_at": pd.Timestamp.utcnow().isoformat(),
              "dataset": "synthetic-v1 (seed 42)",
              "model_version": MODEL_VERSION, "feature_version": FEATURE_VERSION}

    for task, cfg in TASKS.items():
        tgt, ncls = cfg["target"], cfg["n_classes"]
        # Right-censored rows (target == -1) have no observable future window,
        # so they carry no valid label and are dropped from train/val/test.
        # They are still scored at inference — forecasting from "now" is the
        # deployed use case; only supervision requires a known outcome.
        valid = feats[tgt] >= 0
        n_censored = int((~valid).sum())
        if n_censored:
            print(f"[{task}] excluding {n_censored} right-censored rows "
                  f"({n_censored / len(feats):.1%}) with no observable outcome window")
        m = {k: masks[k] & valid for k in masks}
        Xtr = feats.loc[m["train"], fcols].values
        ytr = feats.loc[m["train"], tgt].values
        Xva = feats.loc[m["val"], fcols].values
        yva = feats.loc[m["val"], tgt].values
        Xte = feats.loc[m["test"], fcols].values
        yte = feats.loc[m["test"], tgt].values

        results = {}
        fitted = {}
        for name, model in make_models(ncls, ytr).items():
            if name == "xgboost" and ncls > 2:
                sw = compute_sample_weight("balanced", ytr)
                model.fit(Xtr, ytr, sample_weight=sw)
            else:
                model.fit(Xtr, ytr)
            results[name] = {"val": evaluate(model, Xva, yva, ncls),
                             "test": evaluate(model, Xte, yte, ncls)}
            fitted[name] = model
            print(f"[{task}] {name}: val_f1_macro={results[name]['val']['f1_macro']} "
                  f"val_recall={results[name]['val']['recall_macro']}")

        best = select_best(results, task)
        print(f"[{task}] BEST -> {best}\n")
        with open(MODELS / f"{task}.pkl", "wb") as f:
            pickle.dump({"model": fitted[best], "model_name": best, "task": task,
                         "classes": cfg["classes"], "feature_columns": fcols,
                         "model_version": f"{task[:3].upper()}-{best[:3].upper()}-{MODEL_VERSION}",
                         "feature_version": FEATURE_VERSION,
                         "dataset": "synthetic-v1 (seed 42)",
                         "trained_at": pd.Timestamp.utcnow().isoformat()}, f)

        report["tasks"][task] = {
            "target": tgt, "classes": cfg["classes"], "best_model": best,
            "models": results,
            "class_distribution_train": {int(k): int(v) for k, v in
                                         pd.Series(ytr).value_counts().sort_index().items()},
        }

    with open(MODELS / "report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("saved models + report.json")


if __name__ == "__main__":
    main()
