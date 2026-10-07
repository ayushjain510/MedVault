"""Seed the MedVault database from the synthetic dataset + trained models.

Run from sepsis-ai/backend:  python seed.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import bcrypt

from app.config import DATA_DIR, MODELS_DIR, DB_PATH
from app.database import (Base, engine, SessionLocal, Patient, Vital,
                          AntibioticRecord, Prediction, Alert, User)
from app.services.predictor import load_bundles, TASK_ORDER
from app.alerts.engine import generate_alerts
from app.services.audit import now_iso
from app.services.risk import ensure_risk_scores

sys.path.insert(0, str(DATA_DIR.parent))
from features import feature_columns  # noqa: E402

USERS = [
    ("admin", "admin123", "admin"),
    ("clinician", "clin123", "clinician"),
    ("researcher", "res123", "researcher"),
]


def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    Base.metadata.create_all(engine)
    db = SessionLocal()

    patients = pd.read_csv(DATA_DIR / "patients.csv")
    vitals = pd.read_csv(DATA_DIR / "timeseries.csv")
    abx = pd.read_csv(DATA_DIR / "antibiotics.csv")
    feats = pd.read_parquet(DATA_DIR / "features.parquet")
    fcols = feature_columns(feats)

    for _, r in patients.iterrows():
        db.add(Patient(patient_id=r.patient_id, age=int(r.age), sex=r.sex,
                       archetype=r.archetype, n_hours=int(r.n_hours),
                       admission_offset_hours=int(r.admission_offset_hours), icu=True))
    db.commit()

    vit_cols = ["patient_id", "hour", "heart_rate", "sbp", "dbp", "map", "resp_rate",
                "spo2", "temperature", "lactate", "wbc", "creatinine", "bilirubin",
                "platelets", "urine_output", "fluid_input", "fluid_output"]
    vitals[vit_cols].to_sql("vitals", engine, if_exists="append", index=False)

    for _, r in abx.iterrows():
        db.add(AntibioticRecord(
            patient_id=r.patient_id, start_hour=int(r.start_hour), abx_class=r.abx_class,
            duration_hours=int(r.duration_hours), culture_taken=bool(r.culture_taken),
            culture_positive=bool(r.culture_positive),
            organism=None if pd.isna(r.organism) else r.organism,
            susceptible=bool(r.susceptible)))
    db.commit()

    # Batch predictions for ALL hours (fast vectorized predict per task)
    bundles = load_bundles()
    X = feats[fcols].values
    pred_rows = []
    per_task_labels = {}
    for task in TASK_ORDER:
        b = bundles[task]
        model = b["model"]
        proba = model.predict_proba(X)
        cls_pos = np.argmax(proba, axis=1)
        model_classes = np.array(model.classes_)
        labels_idx = model_classes[cls_pos].astype(int)
        per_task_labels[task] = (labels_idx, proba, model_classes)
        for i in range(len(feats)):
            probs = {b["classes"][int(model_classes[j])]: round(float(proba[i, j]), 4)
                     for j in range(proba.shape[1])}
            pred_rows.append({
                "patient_id": feats["patient_id"].iat[i], "hour": int(feats["hour"].iat[i]),
                "task": task, "predicted_class": int(labels_idx[i]),
                "predicted_label": b["classes"][int(labels_idx[i])],
                "probability": round(float(proba[i, cls_pos[i]]), 4),
                "probabilities_json": json.dumps(probs)})
        print(f"predicted {task}")
    pd.DataFrame(pred_rows).to_sql("predictions", engine, if_exists="append", index=False)

    # Alerts at each patient's latest hour
    last_idx = feats.groupby("patient_id")["hour"].idxmax()
    n_alerts = 0
    for idx in last_idx:
        row = feats.loc[idx]
        pid, hour = row["patient_id"], int(row["hour"])
        preds = {}
        for task in TASK_ORDER:
            b = bundles[task]
            labels_idx, proba, model_classes = per_task_labels[task]
            i = feats.index.get_loc(idx)
            probs = {b["classes"][int(model_classes[j])]: float(proba[i, j])
                     for j in range(proba.shape[1])}
            lab = b["classes"][int(labels_idx[i])]
            preds[task] = {"predicted_class": int(labels_idx[i]), "predicted_label": lab,
                           "probability": float(proba[i].max()), "probabilities": probs}
        for a in generate_alerts(pid, hour, row, preds):
            db.add(Alert(**a))
            n_alerts += 1
    db.commit()
    print(f"alerts: {n_alerts}")

    for username, pw, role in USERS:
        db.add(User(username=username,
                    password_hash=bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode(),
                    role=role, is_active=True, created_at=now_iso()))
    db.commit()

    # MedVault Composite Risk Score for every patient-hour, from the
    # predictions stored above (same code path the API and simulator use).
    ensure_risk_scores(db)
    print("risk scores computed")
    db.close()
    print(f"DB seeded at {DB_PATH}")


if __name__ == "__main__":
    main()
