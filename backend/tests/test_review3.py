"""Review 3 tests: risk score, clinical timeline, scenario simulation,
data-quality monitoring, and role-based services.

Run from medvault/backend:  python -m pytest tests -q
(conftest.py points the app at a temporary copy of the seeded database.)
"""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Patient, Prediction, RiskScore, AuditLog, Alert
from app.services.analytics import data_quality, what_changed, trend_series
from app.services.patient_data import vitals_frame, ALL_FIELDS
from app.services.permissions import ROLE_PERMISSIONS, ROLES, PERMISSIONS, has_permission
from app.services.risk import compute_risk, level_for, MAX_POINTS, BANDS, ENGINE_FLOOR
from app.services.timeline import build_timeline

client = TestClient(app)
CREDS = {"admin": "admin123", "clinician": "clin123", "researcher": "res123"}
_tokens: dict[str, dict] = {}


def auth(role="clinician"):
    if role not in _tokens:
        r = client.post("/api/auth/login", data={"username": role, "password": CREDS[role]})
        assert r.status_code == 200
        _tokens[role] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _tokens[role]


def _patients():
    return client.get("/api/patients", headers=auth()).json()["patients"]


def _pred(label_probs: dict, cls=0):
    lab = max(label_probs, key=label_probs.get)
    return {"predicted_class": cls, "predicted_label": lab,
            "probability": label_probs[lab], "probabilities": label_probs}


SEPSIS = ["Stable", "At Risk", "Active Sepsis", "Severe/Deteriorating",
          "Treatment Response", "Recovery", "Non-responding", "Escalation"]
RT = ["RT-0", "RT-1", "RT-2", "RT-3", "RT-4", "RT-5"]
AR = ["AR-0", "AR-1", "AR-2", "AR-3", "AR-4"]
FS = ["FS-0", "FS-1", "FS-2", "FS-3", "FS-4", "FS-5"]


def _preds(p_det: float, sepsis: str, rt: int, ar: int, fs: int) -> dict:
    def one_hot(names, i):
        return {n: (1.0 if j == i else 0.0) for j, n in enumerate(names)}
    det = lambda h: _pred({"No deterioration": 1 - p_det, f"Deterioration ≤{h}h": p_det})
    return {"deterioration_6h": det(6), "deterioration_12h": det(12), "deterioration_24h": det(24),
            "sepsis_state": _pred(one_hot(SEPSIS, SEPSIS.index(sepsis))),
            "recovery": _pred(one_hot(RT, rt), rt),
            "antibiotic_response": _pred(one_hot(AR, ar), ar),
            "fluid_status": _pred(one_hot(FS, fs), fs)}


# ---------------------------------------------------------------- risk score

def test_risk_weights_sum_to_100_and_bands_cover_range():
    assert sum(MAX_POINTS.values()) == 100
    assert [f for f, _ in BANDS] == [75, 50, 25, 0]
    assert [level_for(s) for s in (0, 24, 25, 49, 50, 74, 75, 100)] == \
        ["LOW", "LOW", "MODERATE", "MODERATE", "HIGH", "HIGH", "CRITICAL", "CRITICAL"]


def test_risk_extremes_stay_in_range():
    best = compute_risk(_preds(0.0, "Stable", 0, 0, 0), 48, trend_score=5.0)
    worst = compute_risk(_preds(1.0, "Escalation", 4, 4, 3), 48, trend_score=-9.0)
    assert best["score"] == 0 and best["level"] == "LOW"
    assert worst["score"] >= 95 and worst["level"] == "CRITICAL"
    for r in (best, worst):
        assert 0 <= r["score"] <= 100
        assert len(r["components"]) == len(MAX_POINTS)


def test_risk_contributors_explain_the_score():
    r = compute_risk(_preds(0.6, "Active Sepsis", 3, 2, 1), 48, trend_score=-1.5)
    assert not r["floor_applied"]
    assert round(sum(c["points"] for c in r["components"])) == r["score"]
    for c in r["components"]:
        assert 0 <= c["points"] <= c["max_points"]
    # sorted by contribution, largest first
    pts = [c["points"] for c in r["components"]]
    assert pts == sorted(pts, reverse=True)


def test_risk_is_monotone_in_deterioration_probability():
    scores = [compute_risk(_preds(p, "At Risk", 1, 1, 0), 48, 0.0)["score"]
              for p in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert scores == sorted(scores) and scores[-1] > scores[0]


def test_risk_missing_predictions_do_not_crash():
    partial = {"deterioration_6h": _pred({"No deterioration": 0.2, "Deterioration ≤6h": 0.8})}
    r = compute_risk(partial, 48, None)
    assert r["renormalised"] and 0 <= r["score"] <= 100
    assert r["score"] == 80           # only available component, rescaled to 0-100
    assert [c["key"] for c in r["components"] if not c["available"]]

    empty = compute_risk({}, 48, None)
    assert empty["score"] is None and empty["level"] == "INSUFFICIENT DATA"


def test_risk_withheld_below_six_hours():
    r = compute_risk(_preds(0.9, "Escalation", 4, 4, 3), 3, None)
    assert r["score"] is None and r["level"] == "INSUFFICIENT DATA"


def test_risk_floor_follows_state_engine():
    # STATE 7 via the safety net (p_det >= 0.85) with otherwise benign outputs
    preds = _preds(0.0, "Stable", 0, 0, 0)
    preds["deterioration_6h"] = _pred({"No deterioration": 0.1, "Deterioration ≤6h": 0.9})
    r = compute_risk(preds, 48, 3.0)
    assert r["engine_state"] == "High-Risk Clinical Trajectory"
    assert r["floor_applied"] and r["score"] == ENGINE_FLOOR and r["raw_score"] < ENGINE_FLOOR
    assert r["level"] == "HIGH"


def test_stored_risk_scores_are_valid():
    db = SessionLocal()
    try:
        rows = db.query(RiskScore.score, RiskScore.level).all()
    finally:
        db.close()
    assert len(rows) > 10000
    for score, level in rows:
        if score is None:
            assert level == "INSUFFICIENT DATA"
        else:
            assert 0 <= score <= 100 and level == level_for(score)


def test_risk_endpoint():
    pid = _patients()[0]["patient_id"]
    r = client.get(f"/api/patients/{pid}/risk", headers=auth())
    assert r.status_code == 200
    d = r.json()
    assert d["patient_id"] == pid
    assert 0 <= d["score"] <= 100 and d["level"] == level_for(d["score"])
    assert len(d["components"]) == 6 and all("label" in c and "value" in c for c in d["components"])
    assert "not a validated clinical score" in d["note"]
    assert d["data_quality"]["score_adjusted"] is False
    assert d["history"][-1]["hour"] == d["hour"]
    # the stored value used by lists/timeline equals the live computation
    assert d["history"][-1]["score"] == d["score"]


def test_risk_endpoint_matches_patient_list():
    pats = _patients()
    for p in pats[:5]:
        d = client.get(f"/api/patients/{p['patient_id']}/risk", headers=auth()).json()
        assert (d["score"], d["level"]) == (p["risk_score"], p["risk_level"])


def test_risk_endpoint_errors():
    assert client.get("/api/patients/NOPE999/risk", headers=auth()).status_code == 404
    assert client.get("/api/patients/bad id!/risk", headers=auth()).status_code == 422
    assert client.get("/api/patients/P0001/risk").status_code == 401


def test_unit_risk_ranking_sorted():
    d = client.get("/api/risk", headers=auth()).json()
    scores = [p["risk_score"] for p in d["patients"] if p["risk_score"] is not None]
    assert scores == sorted(scores, reverse=True)
    assert sum(d["risk_levels"].values()) == len(d["patients"])
    assert d["patients"][0]["top_contributor"]["points"] > 0


def test_trend_series_matches_what_changed():
    db = SessionLocal()
    try:
        for (pid,) in db.query(Patient.patient_id).limit(8):
            vit = vitals_frame(db, pid)
            wc = what_changed(vit)
            assert wc["available"]
            assert abs(trend_series(vit)[-1] - wc["trend_score"]) < 1e-3
    finally:
        db.close()


def test_trend_series_is_causal():
    db = SessionLocal()
    try:
        vit = vitals_frame(db, "P0001")
    finally:
        db.close()
    full = trend_series(vit)
    cut = trend_series(vit.iloc[:30])
    assert np.allclose(full[11:30], cut[11:30])
    assert np.isnan(full[:11]).all()


# ------------------------------------------------------------------ timeline

def test_timeline_is_chronological_and_patient_specific():
    pid = _patients()[0]["patient_id"]
    d = client.get(f"/api/patients/{pid}/timeline", headers=auth()).json()
    hours = [e["hour"] for e in d["events"]]
    assert hours == sorted(hours)
    assert d["patient_id"] == pid and d["events"][0]["type"] == "admission"
    assert all(0 <= h <= d["current_hour"] for h in hours)
    for e in d["events"]:
        assert e["title"] and e["type"] in d["event_types"] and "detail" in e
    assert sum(d["counts"].values()) == len(d["events"])


def test_timeline_represents_alerts_states_and_risk():
    db = SessionLocal()
    try:
        pid = db.query(Alert.patient_id).filter(Alert.severity == "critical").first()[0]
        n_alert_titles = len({a.title for a in db.query(Alert).filter(Alert.patient_id == pid)})
    finally:
        db.close()
    d = client.get(f"/api/patients/{pid}/timeline", headers=auth()).json()
    types = {e["type"] for e in d["events"]}
    assert {"admission", "alert", "state_change", "risk_change"} <= types
    assert d["counts"]["alert"] >= n_alert_titles
    assert any(e["severity"] == "critical" for e in d["events"] if e["type"] == "alert")


def test_timeline_is_not_raw_measurements():
    """Meaningful events only: far fewer events than hourly observations."""
    for p in _patients()[:10]:
        d = client.get(f"/api/patients/{p['patient_id']}/timeline", headers=auth()).json()
        assert len(d["events"]) < p["n_hours"]


def test_timeline_type_filter():
    pid = _patients()[0]["patient_id"]
    d = client.get(f"/api/patients/{pid}/timeline?types=admission,alert", headers=auth()).json()
    assert {e["type"] for e in d["events"]} <= {"admission", "alert"}
    assert client.get(f"/api/patients/{pid}/timeline?types=bogus", headers=auth()).status_code == 400


def test_timeline_empty_patient_and_unknown_patient():
    db = SessionLocal()
    try:
        db.add(Patient(patient_id="TEMPTY", age=50, sex="F", archetype="stable",
                       n_hours=0, admission_offset_hours=0, icu=True))
        db.commit()
        events = build_timeline(db, db.query(Patient).filter(Patient.patient_id == "TEMPTY").one())
        assert [e["type"] for e in events] == ["admission"]
    finally:
        db.query(Patient).filter(Patient.patient_id == "TEMPTY").delete()
        db.commit()
        db.close()
    assert client.get("/api/patients/NOPE999/timeline", headers=auth()).status_code == 404


# ---------------------------------------------------------------- simulation

@pytest.fixture(scope="module")
def simulated():
    """A low-risk patient pushed through 30 'deteriorating' hours."""
    pats = [p for p in _patients() if p["risk_level"] == "LOW" and p["n_hours"] >= 24]
    p = pats[0]
    before = client.get(f"/api/patients/{p['patient_id']}/risk", headers=auth()).json()
    results = [client.post(f"/api/sim/{p['patient_id']}/tick", headers=auth(),
                           json={"scenario": "deteriorating", "hours": 6}).json() for _ in range(5)]
    return {"pid": p["patient_id"], "start_hours": p["n_hours"], "before": before, "results": results}


def test_simulation_requires_permission():
    pid = _patients()[1]["patient_id"]
    body = {"scenario": "stable", "hours": 1}
    assert client.post(f"/api/sim/{pid}/tick", json=body).status_code == 401
    assert client.post(f"/api/sim/{pid}/tick", json=body, headers=auth("admin")).status_code == 403
    assert client.get("/api/sim/scenarios", headers=auth("admin")).status_code == 403
    assert client.post(f"/api/sim/{pid}/tick", json=body, headers=auth("researcher")).status_code == 200


def test_simulation_validates_input():
    pid = _patients()[1]["patient_id"]
    h = auth()
    assert client.post(f"/api/sim/{pid}/tick", json={"scenario": "explode"}, headers=h).status_code == 422
    assert client.post(f"/api/sim/{pid}/tick", json={"hours": 0}, headers=h).status_code == 422
    assert client.post(f"/api/sim/{pid}/tick", json={"hours": 500}, headers=h).status_code == 422
    assert client.post("/api/sim/NOPE999/tick", json={}, headers=h).status_code == 404
    keys = {s["key"] for s in client.get("/api/sim/scenarios", headers=h).json()["scenarios"]}
    assert {"stable", "improving", "deteriorating"} <= keys


def test_simulation_default_body_still_works():
    """The pre-Review-3 call shape: scenario only, one hour."""
    pid = _patients()[2]["patient_id"]
    before = client.get(f"/api/patients/{pid}", headers=auth()).json()["n_hours"]
    d = client.post(f"/api/sim/{pid}/tick", json={"scenario": "continue"}, headers=auth()).json()
    assert d["hour"] == before and d["hours_advanced"] == 1
    assert {"vitals", "predictions", "new_alerts"} <= set(d)
    assert len(d["predictions"]) == 7


def test_simulation_updates_patient_state(simulated):
    pid, last = simulated["pid"], simulated["results"][-1]
    assert last["hour"] == simulated["start_hours"] + 30 - 1
    detail = client.get(f"/api/patients/{pid}", headers=auth()).json()
    assert detail["n_hours"] == simulated["start_hours"] + 30
    vit = client.get(f"/api/patients/{pid}/vitals", headers=auth()).json()["series"]
    assert vit[-1]["hour"] == last["hour"] and len(vit) == detail["n_hours"]


def test_simulation_reruns_all_models_every_hour(simulated):
    db = SessionLocal()
    try:
        for hour in range(simulated["start_hours"], simulated["start_hours"] + 30):
            tasks = {t for (t,) in db.query(Prediction.task).filter(
                Prediction.patient_id == simulated["pid"], Prediction.hour == hour)}
            assert len(tasks) == 7, hour
    finally:
        db.close()
    preds = client.get(f"/api/patients/{simulated['pid']}", headers=auth()).json()["predictions"]
    assert preds["deterioration_6h"]["probabilities"] == \
        simulated["results"][-1]["predictions"]["deterioration_6h"]["probabilities"]


def test_simulation_updates_risk(simulated):
    before, last = simulated["before"], simulated["results"][-1]
    assert simulated["results"][0]["risk_before"]["score"] == before["score"]
    risk = client.get(f"/api/patients/{simulated['pid']}/risk", headers=auth()).json()
    assert risk["hour"] == last["hour"] and risk["score"] == last["risk"]["score"]
    assert len(risk["history"]) == len(before["history"]) + 30
    # a deteriorating scenario must actually raise the pipeline's risk
    peak = max(s["risk_score"] for r in simulated["results"] for s in r["steps"])
    assert peak >= before["score"] + 25
    assert risk["score"] > before["score"]


def test_simulation_updates_timeline_and_alerts(simulated):
    d = client.get(f"/api/patients/{simulated['pid']}/timeline", headers=auth()).json()
    sims = [e for e in d["events"] if e["type"] == "simulation"]
    assert len(sims) == 1                                   # 30 ticks collapsed into one run
    assert sims[0]["hour"] == simulated["start_hours"] and sims[0]["scenario"] == "deteriorating"
    assert sims[0]["until_hour"] == simulated["start_hours"] + 29
    later = [e for e in d["events"] if e["hour"] >= simulated["start_hours"]]
    assert all(e["simulated"] for e in later)
    assert any(e["type"] == "risk_change" for e in later)
    new_alerts = [a for r in simulated["results"] for a in r["new_alerts"]]
    assert any(a["severity"] in ("high", "critical") for a in new_alerts)
    assert any(e["type"] == "alert" for e in later)
    hours = [e["hour"] for e in d["events"]]
    assert hours == sorted(hours)


def test_simulation_improving_lowers_risk(simulated):
    pid = simulated["pid"]
    start = client.get(f"/api/patients/{pid}/risk", headers=auth()).json()["score"]
    for _ in range(5):
        last = client.post(f"/api/sim/{pid}/tick", headers=auth(),
                           json={"scenario": "improving", "hours": 6}).json()
    assert last["risk"]["score"] < start - 15


def test_simulation_alerts_never_order_treatment(simulated):
    alerts = client.get("/api/alerts", headers=auth()).json()["alerts"]
    assert any(a["category"] == "RISK SCORE" for a in alerts)
    banned = ["administer", "give ", "prescribe", "switch antibiotic", "bolus", "dose"]
    for a in alerts:
        text = (a["title"] + a["message"]).lower()
        assert not any(b in text for b in banned), text


# -------------------------------------------------------------- data quality

def _frame(n=24, **overrides):
    df = pd.DataFrame({c: np.full(n, 1.0) for c in ALL_FIELDS})
    df["patient_id"], df["hour"] = "T", np.arange(n)
    for col, values in overrides.items():
        df[col] = values
    return df


def test_data_quality_complete_record_has_no_warnings():
    q = data_quality(_frame(), has_abx=True)
    assert q["overall_score"] == 100 and q["level"] == "GOOD" and q["warnings"] == []
    assert q["lab_timeliness"] == 100 and q["missing_latest"] == []


def test_data_quality_detects_stale_lab():
    creat = np.full(24, np.nan)
    creat[9] = 1.1                                   # last measured at hour 9 of 0..23
    q = data_quality(_frame(creatinine=creat), has_abx=True)
    w = next(w for w in q["warnings"] if w["code"] == "stale_lab")
    assert w["variable"] == "creatinine" and w["hours_ago"] == 14 and w["last_hour"] == 9
    assert "14 hours ago" in w["message"]
    assert q["stale_labs_hours"]["creatinine"] == 14 and q["lab_timeliness"] == 80
    # the existing penalty for stale labs still applies to the overall score
    assert q["overall_score"] < data_quality(_frame(), True)["overall_score"]


def test_data_quality_detects_missing_data():
    hr = np.full(24, 80.0)
    hr[-3:] = np.nan
    lact = np.full(24, np.nan)
    q = data_quality(_frame(heart_rate=hr, map=hr.copy(), lactate=lact), has_abx=False)
    codes = {w["code"] for w in q["warnings"]}
    assert {"missing_latest", "never_measured", "recent_vitals_gap", "no_antibiotic_record"} <= codes
    assert q["missing_latest"] == ["heart_rate", "map"]
    assert q["missing_counts"] == {"heart_rate": 3, "map": 3}
    assert q["sections"]["recent_vitals_6h"] < 90
    assert q["last_measured_hour"]["lactate"] is None
    assert q["sections"]["antibiotic_data"] == 0.0


def test_data_quality_insufficient_history():
    q = data_quality(_frame(n=4), has_abx=True)
    assert not q["sufficient"]
    assert any(w["code"] == "insufficient_history" for w in q["warnings"])


def test_data_quality_existing_formula_unchanged():
    """The Review-3 additions must not alter the original score."""
    db = SessionLocal()
    try:
        vit = vitals_frame(db, "P0001")
    finally:
        db.close()
    q = data_quality(vit, True)
    s = q["sections"]
    expected = (0.4 * s["vitals"] + 0.3 * s["laboratory"] + 0.2 * s["fluid_records"]
                + 0.1 * s["recent_vitals_6h"]) / 100
    if max(q["stale_labs_hours"].values()) > 12:
        expected *= 0.85
    assert q["overall_score"] == round(expected * 100)
    assert q["confidence_modifier"] == round(expected, 3)


def test_data_quality_endpoints():
    h = auth()
    d = client.get("/api/patients/P0001/data-quality", headers=h).json()
    for key in ("overall_score", "level", "sections", "stale_labs_hours", "warnings",
                "hours_of_data", "lab_timeliness", "missing_latest"):
        assert key in d
    assert d["patient_id"] == "P0001"
    assert client.get("/api/patients/NOPE999/data-quality", headers=h).status_code == 404

    unit = client.get("/api/data-quality", headers=h).json()
    row = next(r for r in unit["patients"] if r["patient_id"] == "P0001")
    assert row["overall_score"] == d["overall_score"] and row["level"] == d["level"]
    assert sum(unit["levels"].values()) == len(unit["patients"])


# --------------------------------------------------- role-based services

# (method, path, required permission) for every protected service
SERVICES = [
    ("GET", "/api/patients", "patients.view"),
    ("GET", "/api/patients/P0001", "patients.view"),
    ("GET", "/api/patients/P0001/vitals", "patients.view"),
    ("GET", "/api/patients/P0001/labs", "patients.view"),
    ("GET", "/api/patients/P0001/fluids", "patients.view"),
    ("GET", "/api/patients/P0001/antibiotics", "patients.view"),
    ("GET", "/api/patients/P0001/predictions", "patients.view"),
    ("GET", "/api/patients/P0001/state", "patients.view"),
    ("GET", "/api/patients/P0001/what-changed", "patients.view"),
    ("GET", "/api/patients/P0001/similar", "patients.view"),
    ("GET", "/api/overview", "patients.view"),
    ("GET", "/api/patients/P0001/risk", "risk.view"),
    ("GET", "/api/risk", "risk.view"),
    ("GET", "/api/patients/P0001/timeline", "timeline.view"),
    ("GET", "/api/alerts", "alerts.view"),
    ("GET", "/api/patients/P0001/data-quality", "data_quality.view"),
    ("GET", "/api/data-quality", "data_quality.view"),
    ("GET", "/api/explanations/P0001?task=fluid_status", "explainability.view"),
    ("GET", "/api/sim/scenarios", "simulation.run"),
    ("GET", "/api/models", "models.view"),
    ("GET", "/api/model-performance", "models.evaluate"),
    ("GET", "/api/dashboard/clinician", "patients.monitor"),
    ("GET", "/api/dashboard/researcher", "models.evaluate"),
    ("GET", "/api/research/trajectories", "trajectory.view"),
    ("GET", "/api/admin/dashboard", "system.view"),
    ("GET", "/api/admin/users", "users.view"),
    ("GET", "/api/admin/roles", "roles.view"),
    ("GET", "/api/admin/audit", "audit.view"),
    ("GET", "/api/admin/system-health", "system.view"),
    ("GET", "/api/admin/settings", "system.view"),
]


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("method,path,perm", SERVICES)
def test_every_role_against_every_service(role, method, path, perm):
    expected = 200 if has_permission(role, perm) else 403
    assert client.request(method, path, headers=auth(role)).status_code == expected


@pytest.mark.parametrize("method,path,perm", SERVICES)
def test_every_service_requires_authentication(method, path, perm):
    assert client.request(method, path).status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.request(method, path, headers=bad).status_code == 401


def test_role_service_boundaries():
    """The intended separation, stated explicitly rather than derived."""
    allow = lambda role, perm: has_permission(role, perm)
    admin_only = ["users.view", "users.create", "users.update", "roles.view", "audit.view", "system.view"]
    for perm in admin_only:
        assert allow("admin", perm) and not allow("clinician", perm) and not allow("researcher", perm)
    assert allow("clinician", "simulation.run") and allow("researcher", "simulation.run")
    assert not allow("admin", "simulation.run")             # admin is not a superuser
    assert not allow("admin", "models.evaluate") and not allow("admin", "explainability.view")
    assert allow("researcher", "models.evaluate") and not allow("clinician", "models.evaluate")
    assert allow("clinician", "patients.monitor") and not allow("researcher", "patients.monitor")
    assert allow("clinician", "alerts.acknowledge") and not allow("researcher", "alerts.acknowledge")
    assert all(p in PERMISSIONS for perms in ROLE_PERMISSIONS.values() for p in perms)


def test_login_returns_permissions_and_me_matches():
    for role in ROLES:
        r = client.post("/api/auth/login", data={"username": role, "password": CREDS[role]}).json()
        assert r["role"] == role and set(r["permissions"]) == ROLE_PERMISSIONS[role]
        me = client.get("/api/auth/me", headers=auth(role)).json()
        assert me["username"] == role and set(me["permissions"]) == ROLE_PERMISSIONS[role]


def test_dashboards_return_live_numbers():
    pats = _patients()
    c = client.get("/api/dashboard/clinician", headers=auth("clinician")).json()
    assert c["total_patients"] == len(pats)
    assert c["critical_patients"] == sum(1 for p in pats if p["risk_level"] == "CRITICAL")
    assert c["high_risk_patients"] == sum(1 for p in pats if p["risk_level"] == "HIGH")
    assert sum(c["risk_levels"].values()) == len(pats)

    r = client.get("/api/dashboard/researcher", headers=auth("researcher")).json()
    assert r["n_patients"] == len(pats) and r["n_prediction_tasks"] == 7
    assert r["n_observations"] == sum(p["n_hours"] for p in pats)
    assert {t["task"] for t in r["prediction_tasks"]} == set(
        client.get("/api/models", headers=auth("researcher")).json()["tasks"])

    a = client.get("/api/admin/dashboard", headers=auth("admin")).json()
    assert a["users"]["total"] >= 3 and a["users"]["by_role"]["admin"] >= 1
    assert a["system"]["database"]["status"] == "ok"
    assert a["system"]["model_service"]["loaded"] == 7


def test_alert_acknowledgement_by_role():
    alert_id = client.get("/api/alerts", headers=auth()).json()["alerts"][0]["id"]
    assert client.post(f"/api/alerts/{alert_id}/acknowledge", headers=auth("researcher")).status_code == 403
    assert client.post(f"/api/alerts/{alert_id}/acknowledge", headers=auth("admin")).status_code == 403
    assert client.post(f"/api/alerts/{alert_id}/acknowledge", headers=auth("clinician")).status_code == 200
    assert client.post("/api/alerts/99999999/acknowledge", headers=auth("clinician")).status_code == 404
    alerts = client.get("/api/alerts", headers=auth()).json()["alerts"]
    assert next(a for a in alerts if a["id"] == alert_id)["acknowledged"] is True


# ------------------------------------------------------- admin user services

def test_admin_user_lifecycle():
    h = auth("admin")
    new = {"username": "test.nurse", "password": "s3cret-pass", "role": "clinician"}
    for role in ("clinician", "researcher"):
        assert client.post("/api/admin/users", json=new, headers=auth(role)).status_code == 403
    r = client.post("/api/admin/users", json=new, headers=h)
    assert r.status_code == 201
    uid = r.json()["id"]
    assert "password" not in r.json() and "password_hash" not in r.json()
    assert client.post("/api/admin/users", json=new, headers=h).status_code == 409

    login = lambda pw="s3cret-pass": client.post(
        "/api/auth/login", data={"username": "test.nurse", "password": pw})
    tok = {"Authorization": f"Bearer {login().json()['access_token']}"}
    assert client.get("/api/dashboard/clinician", headers=tok).status_code == 200
    assert client.get("/api/model-performance", headers=tok).status_code == 403

    # role change takes effect on the very next request (role is read from the DB)
    assert client.patch(f"/api/admin/users/{uid}", json={"role": "researcher"}, headers=h).status_code == 200
    assert client.get("/api/model-performance", headers=tok).status_code == 200
    assert client.get("/api/dashboard/clinician", headers=tok).status_code == 403

    assert client.patch(f"/api/admin/users/{uid}", json={"password": "another-pass-9"}, headers=h).status_code == 200
    assert login().status_code == 401 and login("another-pass-9").status_code == 200

    # deactivation: existing token dies, login is refused
    assert client.patch(f"/api/admin/users/{uid}", json={"is_active": False}, headers=h).status_code == 200
    assert client.get("/api/patients", headers=tok).status_code == 401
    assert login("another-pass-9").status_code == 403
    assert client.patch(f"/api/admin/users/{uid}", json={"is_active": True}, headers=h).status_code == 200
    assert login("another-pass-9").status_code == 200


def test_admin_user_validation_and_guards():
    h = auth("admin")
    bad = [{"username": "ab", "password": "longenough1", "role": "clinician"},
           {"username": "ok_name", "password": "short", "role": "clinician"},
           {"username": "ok_name", "password": "longenough1", "role": "superuser"},
           {"username": "bad name!", "password": "longenough1", "role": "clinician"}]
    for body in bad:
        assert client.post("/api/admin/users", json=body, headers=h).status_code == 422
    users = client.get("/api/admin/users", headers=h).json()["users"]
    me = next(u for u in users if u["username"] == "admin")
    assert client.patch(f"/api/admin/users/{me['id']}", json={"is_active": False}, headers=h).status_code == 400
    assert client.patch(f"/api/admin/users/{me['id']}", json={"role": "clinician"}, headers=h).status_code == 400
    assert client.patch("/api/admin/users/999999", json={"role": "clinician"}, headers=h).status_code == 404
    assert all("password_hash" not in u for u in users)


def test_audit_log_records_actions_without_secrets():
    h = auth("admin")
    client.post("/api/auth/login", data={"username": "clinician", "password": "definitely-wrong"})
    client.get("/api/admin/users", headers=auth("researcher"))          # denied
    pid = _patients()[3]["patient_id"]
    client.get(f"/api/patients/{pid}", headers=auth("clinician"))
    client.post(f"/api/sim/{pid}/tick", json={"scenario": "stable", "hours": 1}, headers=auth("clinician"))
    client.get("/api/model-performance", headers=auth("researcher"))

    events = client.get("/api/admin/audit?limit=500", headers=h).json()["events"]
    actions = {e["action"] for e in events}
    assert {"auth.login", "patient.view", "simulation.advance", "access.denied",
            "models.analysis_view", "user.create", "user.role_change"} <= actions
    assert any(e["action"] == "auth.login" and e["status"] == "failed" for e in events)
    assert any(e["action"] == "access.denied" and e["status"] == "denied"
               and e["username"] == "researcher" for e in events)
    sim = next(e for e in events if e["action"] == "simulation.advance" and e["target"] == pid)
    assert sim["username"] == "clinician" and "scenario=stable" in sim["detail"]

    db = SessionLocal()
    try:
        blob = " ".join(f"{r.target} {r.detail}" for r in db.query(AuditLog).all())
    finally:
        db.close()
    for secret in ("definitely-wrong", "s3cret-pass", "another-pass-9", "clin123", "Bearer", "eyJ"):
        assert secret not in blob

    assert client.get("/api/admin/audit?status=denied", headers=h).json()["total"] >= 1
    assert client.get("/api/admin/audit?status=nonsense", headers=h).status_code == 422


def test_system_health_and_settings_expose_no_secrets():
    h = auth("admin")
    health = client.get("/api/admin/system-health", headers=h).json()
    assert health["status"] == "ok" and all(m["loaded"] for m in health["models"])
    assert health["counts"]["patients"] >= 240
    settings = client.get("/api/admin/settings", headers=h)
    text = settings.text.lower()
    assert "dev-only-secret" not in text and '"password_hash"' not in text
    assert settings.json()["authentication"]["password_hashing"] == "bcrypt"
