"""End-to-end tests: data pipeline -> features -> models -> API -> alerts.

Run from sepsis-ai/backend:  python -m pytest tests -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "backend"))
sys.path.insert(0, str(BASE / "ml"))

from app.main import app  # noqa: E402
from features import build_features, feature_columns  # noqa: E402
from train import patient_split  # noqa: E402

client = TestClient(app)


def _token(user="clinician", pw="clin123"):
    r = client.post("/api/auth/login", data={"username": user, "password": pw})
    assert r.status_code == 200
    return r.json()["access_token"]


def auth(user="clinician", pw="clin123"):
    return {"Authorization": f"Bearer {_token(user, pw)}"}


# ---------- ML pipeline tests ----------

def test_patient_level_split_no_overlap():
    patients = pd.read_csv(BASE / "ml/data/patients.csv")
    tr, va, te = patient_split(patients)
    assert not set(tr) & set(va)
    assert not set(tr) & set(te)
    assert not set(va) & set(te)
    assert len(tr) + len(va) + len(te) == len(patients)


def test_features_no_leakage_columns():
    feats = pd.read_parquet(BASE / "ml/data/features.parquet")
    fcols = feature_columns(feats)
    assert "severity" not in fcols          # latent ground truth must not leak
    assert not any(c.startswith("y_") for c in fcols)
    assert "state" not in fcols


def test_features_are_causal():
    """A feature at hour h must not change when future rows are removed."""
    vitals = pd.read_csv(BASE / "ml/data/timeseries.csv")
    patients = pd.read_csv(BASE / "ml/data/patients.csv")
    abx = pd.read_csv(BASE / "ml/data/antibiotics.csv")
    pid = patients["patient_id"].iloc[0]
    v = vitals[vitals["patient_id"] == pid]
    full = build_features(v, patients[patients["patient_id"] == pid], abx)
    trunc = build_features(v[v["hour"] <= 20], patients[patients["patient_id"] == pid], abx)
    fcols = [c for c in feature_columns(full) if c in trunc.columns]
    a = full[full["hour"] == 20][fcols].reset_index(drop=True)
    b = trunc[trunc["hour"] == 20][fcols].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_models_load_and_predict():
    from app.services.predictor import load_bundles
    feats = pd.read_parquet(BASE / "ml/data/features.parquet")
    row = feats.iloc[[100]]
    for task, bundle in load_bundles().items():
        proba = bundle["model"].predict_proba(row[bundle["feature_columns"]].values)
        assert np.isclose(proba.sum(), 1, atol=1e-4), task


# ---------- API tests ----------

def test_health_declares_synthetic():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["data"] == "synthetic"


def test_login_rejects_bad_password():
    r = client.post("/api/auth/login", data={"username": "clinician", "password": "wrong"})
    assert r.status_code == 401


def test_endpoints_require_auth():
    for path in ["/api/patients", "/api/alerts", "/api/overview"]:
        assert client.get(path).status_code == 401


def test_role_based_access():
    r = client.get("/api/model-performance", headers=auth("clinician", "clin123"))
    assert r.status_code == 403
    r = client.get("/api/model-performance", headers=auth("researcher", "res123"))
    assert r.status_code == 200


def test_patient_flow():
    h = auth()
    pats = client.get("/api/patients", headers=h).json()["patients"]
    assert len(pats) >= 200
    pid = pats[0]["patient_id"]
    for sub in ["", "/vitals", "/labs", "/fluids", "/antibiotics", "/timeline", "/predictions"]:
        assert client.get(f"/api/patients/{pid}{sub}", headers=h).status_code == 200


def test_explanation_endpoint():
    h = auth()
    r = client.get("/api/explanations/P0001?task=sepsis_state", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert len(d["factors"]) > 0
    assert "disclaimer" in d


def test_predictions_expose_probabilities():
    h = auth()
    d = client.get("/api/patients/P0001/predictions?task=sepsis_state", headers=h).json()
    rows = d["tasks"]["sepsis_state"]
    assert all(0 <= r["probability"] <= 1 for r in rows)


def test_alerts_have_no_treatment_orders():
    h = auth()
    alerts = client.get("/api/alerts", headers=h).json()["alerts"]
    assert len(alerts) > 0
    banned = ["administer", "give ", "prescribe", "switch antibiotic", "bolus"]
    for a in alerts[:200]:
        text = (a["title"] + a["message"]).lower()
        assert not any(b in text for b in banned), text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
