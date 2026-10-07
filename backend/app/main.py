import os
import json
import sys
from typing import Literal

import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, Query, Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .config import DISCLAIMER, ML_DIR
from .database import (get_db, Patient, Vital, AntibioticRecord, Prediction,
                       Alert, User, ensure_schema)
from .services import audit
from .services.auth import verify_password, create_token, get_current_user
from .services.permissions import require_permission, permissions_for
from .services.predictor import (load_report, load_global_importance,
                                 compute_features_for_patient, explain_prediction,
                                 TASK_ORDER)
from .services.simulator import tick, SCENARIO_DRIFT
from .services.state_engine import compute_state, treatment_response_index, recovery_score
from .services.analytics import data_quality, what_changed, similar_trajectories
from .services.patient_data import (latest_predictions, vitals_frame, abx_frame,
                                    VITAL_FIELDS, LAB_FIELDS, FLUID_FIELDS)
from .services.risk import patient_risk, latest_risk_map, LABEL as RISK_LABEL, NOTE as RISK_NOTE
from .services.timeline import build_timeline, EVENT_TYPES
from .services.dashboards import (clinician_dashboard, researcher_dashboard,
                                  trajectory_analysis, risk_ranking, risk_level_counts)
from .admin import router as admin_router

sys.path.insert(0, str(ML_DIR))

app = FastAPI(title="MedVault", version="3.0.0",
              description="Clinical decision-support research prototype. " + DISCLAIMER)

# Local dev origins by default; set ALLOWED_ORIGINS (comma-separated) when the
# frontend is deployed on a different host than the API.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
_origins = [o if o.startswith("http") else f"https://{o}" for o in _origins]
ALLOWED_ORIGINS = _origins or ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

# Adds the Review-3 tables/columns to a database seeded by an earlier version.
ensure_schema()
app.include_router(admin_router)

PID = PathParam(..., min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    permissions: list[str] = []


@app.get("/api/health")
def health():
    return {"status": "ok", "disclaimer": DISCLAIMER, "data": "synthetic"}


@app.post("/api/auth/login", response_model=LoginResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        audit.log_event(db, None, "auth.login", status="failed",
                        username=form.username[:32], detail="invalid credentials")
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    if user.is_active is False:
        audit.log_event(db, user, "auth.login", status="denied", detail="account deactivated")
        raise HTTPException(status_code=403, detail="This account has been deactivated")
    audit.log_event(db, user, "auth.login")
    return LoginResponse(access_token=create_token(user.username, user.role),
                         role=user.role, username=user.username,
                         permissions=permissions_for(user.role))


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    """The caller's identity and effective permissions (drives the UI; the
    API re-checks every request)."""
    return {"username": user.username, "role": user.role,
            "permissions": permissions_for(user.role)}


@app.post("/api/auth/logout")
def logout(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Tokens are stateless, so this only records the sign-out in the audit log."""
    audit.log_event(db, user, "auth.logout")
    return {"status": "ok"}


def _get_patient(db: Session, pid: str) -> Patient:
    p = db.query(Patient).filter(Patient.patient_id == pid).first()
    if not p:
        raise HTTPException(404, "Patient not found")
    return p


_latest_predictions = latest_predictions


def _alert_level(db: Session, pid: str) -> str:
    sevs = [a.severity for a in db.query(Alert).filter(Alert.patient_id == pid).all()]
    for level in ("critical", "high", "moderate"):
        if level in sevs:
            return level
    return "info" if sevs else "none"


def _patient_rows(db: Session) -> list[dict]:
    pats = db.query(Patient).all()
    risk = latest_risk_map(db)
    out = []
    for p in pats:
        preds = _latest_predictions(db, p.patient_id)
        det = preds.get("deterioration_6h", {})
        engine = compute_state(preds, p.n_hours)
        r = risk.get(p.patient_id)
        out.append({
            "engine_state": engine["label"], "engine_tone": engine["tone"],
            "patient_id": p.patient_id, "age": p.age, "sex": p.sex,
            "icu": p.icu, "n_hours": p.n_hours,
            "state": preds.get("sepsis_state", {}).get("predicted_label"),
            "state_prob": preds.get("sepsis_state", {}).get("probability"),
            "det6_risk": det.get("probabilities", {}).get("Deterioration ≤6h"),
            "abx_response": preds.get("antibiotic_response", {}).get("predicted_label"),
            "fluid_status": preds.get("fluid_status", {}).get("predicted_label"),
            "recovery": preds.get("recovery", {}).get("predicted_label"),
            "alert_level": _alert_level(db, p.patient_id),
            "last_hour": p.n_hours - 1,
            "risk_score": r.score if r else None,
            "risk_level": r.level if r else None,
        })
    return out


@app.get("/api/patients")
def list_patients(db: Session = Depends(get_db),
                  user: User = Depends(require_permission("patients.view"))):
    return {"patients": _patient_rows(db), "disclaimer": DISCLAIMER}


@app.get("/api/patients/{pid}")
def patient_detail(pid: str = PID, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("patients.view"))):
    p = _get_patient(db, pid)
    audit.log_event(db, user, "patient.view", target=pid, throttle=True)
    return {"patient_id": p.patient_id, "age": p.age, "sex": p.sex, "icu": p.icu,
            "n_hours": p.n_hours, "admission_offset_hours": p.admission_offset_hours,
            "predictions": _latest_predictions(db, pid),
            "alert_level": _alert_level(db, pid)}


def _series(db: Session, pid: str, fields: list[str]):
    rows = (db.query(Vital).filter(Vital.patient_id == pid).order_by(Vital.hour).all())
    if not rows:
        raise HTTPException(404, "Patient not found")
    return [{"hour": r.hour, **{f: getattr(r, f) for f in fields}} for r in rows]


@app.get("/api/patients/{pid}/vitals")
def patient_vitals(pid: str = PID, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("patients.view"))):
    return {"series": _series(db, pid, VITAL_FIELDS)}


@app.get("/api/patients/{pid}/labs")
def patient_labs(pid: str = PID, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("patients.view"))):
    return {"series": _series(db, pid, LAB_FIELDS)}


@app.get("/api/patients/{pid}/fluids")
def patient_fluids(pid: str = PID, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("patients.view"))):
    rows = _series(db, pid, FLUID_FIELDS)
    cum = 0.0
    for r in rows:
        net = (r["fluid_input"] or 0) - (r["fluid_output"] or 0)
        cum += net
        r["net"] = round(net, 1)
        r["cumulative_balance"] = round(cum, 1)
    return {"series": rows}


@app.get("/api/patients/{pid}/antibiotics")
def patient_abx(pid: str = PID, db: Session = Depends(get_db),
                user: User = Depends(require_permission("patients.view"))):
    rows = db.query(AntibioticRecord).filter(AntibioticRecord.patient_id == pid).all()
    return {"records": [{
        "start_hour": r.start_hour, "abx_class": r.abx_class,
        "duration_hours": r.duration_hours, "culture_taken": r.culture_taken,
        "culture_positive": r.culture_positive, "organism": r.organism,
        "susceptible": r.susceptible} for r in rows]}


@app.get("/api/patients/{pid}/predictions")
def patient_predictions(pid: str = PID, task: str | None = None,
                        db: Session = Depends(get_db),
                        user: User = Depends(require_permission("patients.view"))):
    if task is not None and task not in TASK_ORDER:
        raise HTTPException(400, f"task must be one of {TASK_ORDER}")
    q = db.query(Prediction).filter(Prediction.patient_id == pid)
    if task:
        q = q.filter(Prediction.task == task)
    rows = q.order_by(Prediction.hour).all()
    out = {}
    for r in rows:
        out.setdefault(r.task, []).append({
            "hour": r.hour, "predicted_class": r.predicted_class,
            "predicted_label": r.predicted_label, "probability": r.probability,
            "probabilities": json.loads(r.probabilities_json)})
    return {"tasks": out}


@app.get("/api/patients/{pid}/timeline")
def patient_timeline(pid: str = PID,
                     types: str | None = Query(None, max_length=200,
                                               description="comma-separated event types"),
                     db: Session = Depends(get_db),
                     user: User = Depends(require_permission("timeline.view"))):
    """Chronological clinical timeline aggregated from the stored record
    (see services/timeline.py for the event sources)."""
    p = _get_patient(db, pid)
    events = build_timeline(db, p)
    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    if types:
        wanted = {t.strip() for t in types.split(",") if t.strip()}
        unknown = wanted - set(EVENT_TYPES)
        if unknown:
            raise HTTPException(400, f"unknown event type(s): {sorted(unknown)}")
        events = [e for e in events if e["type"] in wanted]
    return {"patient_id": pid, "current_hour": p.n_hours - 1, "events": events,
            "counts": counts, "event_types": EVENT_TYPES}


@app.get("/api/patients/{pid}/risk")
def patient_risk_score(pid: str = PID, db: Session = Depends(get_db),
                       user: User = Depends(require_permission("risk.view"))):
    """MedVault Composite Risk Score with its contributors (services/risk.py)."""
    return {**patient_risk(db, _get_patient(db, pid)), "disclaimer": DISCLAIMER}


@app.get("/api/risk")
def unit_risk(db: Session = Depends(get_db),
              user: User = Depends(require_permission("risk.view"))):
    """Unit-wide risk ranking: score, 6h change and largest contributor per patient."""
    rows = _patient_rows(db)
    return {"patients": risk_ranking(db, rows), "risk_levels": risk_level_counts(rows),
            "label": RISK_LABEL, "note": RISK_NOTE}


@app.get("/api/alerts")
def list_alerts(severity: Literal["critical", "high", "moderate", "info"] | None = None,
                db: Session = Depends(get_db),
                user: User = Depends(require_permission("alerts.view"))):
    q = db.query(Alert)
    if severity:
        q = q.filter(Alert.severity == severity)
    rows = q.order_by(Alert.id.desc()).limit(400).all()
    return {"alerts": [{
        "id": a.id, "patient_id": a.patient_id, "hour": a.hour,
        "severity": a.severity, "category": a.category, "title": a.title,
        "message": a.message, "variable": a.variable,
        "confidence": a.confidence, "acknowledged": a.acknowledged} for a in rows]}


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int = PathParam(..., ge=1), db: Session = Depends(get_db),
                      user: User = Depends(require_permission("alerts.acknowledge"))):
    a = db.query(Alert).filter(Alert.id == alert_id).first()
    if not a:
        raise HTTPException(404, "Alert not found")
    if not a.acknowledged:
        a.acknowledged = True
        db.commit()
        audit.log_event(db, user, "alert.acknowledge", target=a.patient_id,
                        detail=f"alert {a.id}: {a.title}")
    return {"id": a.id, "acknowledged": True}


@app.get("/api/overview")
def overview(db: Session = Depends(get_db),
             user: User = Depends(require_permission("patients.view"))):
    pats = _patient_rows(db)

    def label(p, key):
        return p.get(key) or ""

    return {
        "total_patients": len(pats),
        "high_concern": len([p for p in pats if p["engine_state"] == "High-Risk Clinical Trajectory"
                             or (p["det6_risk"] or 0) >= 0.75]),
        "poor_recovery": len([p for p in pats if label(p, "recovery").startswith(("RT-3", "RT-4"))]),
        "poor_response": len([p for p in pats if label(p, "abx_response").startswith(("AR-3", "AR-4"))]),
        "fluid_concern": len([p for p in pats if label(p, "fluid_status").startswith(("FS-2", "FS-3", "FS-4"))]),
        "improving": len([p for p in pats if label(p, "recovery").startswith("RT-0")
                          or p["engine_state"] in ("Improving / Recovery", "Treatment Response")]),
        "monitoring": len([p for p in pats if p["engine_state"] in ("Monitoring Required",
                                                                    "Treatment Response Uncertain")]),
        "needs_review": len([p for p in pats if p["alert_level"] in ("critical", "high")]),
        "avg_det6_risk": round(sum((p["det6_risk"] or 0) for p in pats) / max(len(pats), 1), 3),
        "risk_levels": risk_level_counts(pats),
        "disclaimer": DISCLAIMER,
    }


def _vit_df(db: Session, pid: str) -> pd.DataFrame:
    df = vitals_frame(db, pid)
    if df.empty:
        raise HTTPException(404, "Patient not found")
    return df


@app.get("/api/patients/{pid}/microbiology")
def patient_microbiology(pid: str = PID, db: Session = Depends(get_db),
                         user: User = Depends(require_permission("patients.view"))):
    rows = db.query(AntibioticRecord).filter(AntibioticRecord.patient_id == pid).all()
    return {"cultures": [{
        "collected_hour": max(r.start_hour - 2, 0),  # cultures drawn before abx start
        "specimen": "blood", "organism": r.organism,
        "culture_positive": r.culture_positive,
        "susceptible": r.susceptible if r.culture_positive else None,
        "result_available_hour": max(r.start_hour - 2, 0) + 24}
        for r in rows if r.culture_taken]}


@app.get("/api/patients/{pid}/state")
def patient_state(pid: str = PID, db: Session = Depends(get_db),
                  user: User = Depends(require_permission("patients.view"))):
    p = _get_patient(db, pid)
    preds = _latest_predictions(db, pid)
    return {"engine": compute_state(preds, p.n_hours),
            "treatment_response_index": treatment_response_index(preds),
            "predictions": preds,
            "note": "The overall state is a rule-based combination of model outputs "
                    "(dashboard interpretation), distinct from the ML predictions themselves."}


@app.get("/api/patients/{pid}/recovery-trajectory")
def patient_recovery_trajectory(pid: str = PID, db: Session = Depends(get_db),
                                user: User = Depends(require_permission("patients.view"))):
    """Recovery-trajectory score (0-100) per hour, derived from the recovery
    model's probability distribution — the platform's primary longitudinal view."""
    rows = (db.query(Prediction)
            .filter(Prediction.patient_id == pid, Prediction.task == "recovery")
            .order_by(Prediction.hour).all())
    if not rows:
        raise HTTPException(404, "Patient not found")
    series = [{"hour": r.hour,
               "score": recovery_score(json.loads(r.probabilities_json)),
               "label": r.predicted_label} for r in rows]
    return {"series": series,
            "note": ("Probability-weighted favourability of the recovery model's output "
                     "distribution. Model-derived, not a validated clinical score.")}


def _has_abx(db: Session, pid: str) -> bool:
    return db.query(AntibioticRecord).filter(AntibioticRecord.patient_id == pid).count() > 0


@app.get("/api/patients/{pid}/data-quality")
def patient_data_quality(pid: str = PID, db: Session = Depends(get_db),
                         user: User = Depends(require_permission("data_quality.view"))):
    return {"patient_id": pid, **data_quality(_vit_df(db, pid), _has_abx(db, pid))}


@app.get("/api/patients/{pid}/what-changed")
def patient_what_changed(pid: str = PID, window: int = Query(6, ge=3, le=24),
                         db: Session = Depends(get_db),
                         user: User = Depends(require_permission("patients.view"))):
    return what_changed(_vit_df(db, pid), window)


@app.get("/api/patients/{pid}/similar")
def patient_similar(pid: str = PID, db: Session = Depends(get_db),
                    user: User = Depends(require_permission("patients.view"))):
    return similar_trajectories(pid, _vit_df(db, pid))


@app.get("/api/data-quality")
def unit_data_quality(db: Session = Depends(get_db),
                      user: User = Depends(require_permission("data_quality.view"))):
    pats = db.query(Patient).all()
    out = []
    for p in pats:
        q = data_quality(_vit_df(db, p.patient_id), _has_abx(db, p.patient_id))
        out.append({"patient_id": p.patient_id, "overall_score": q["overall_score"],
                    "sufficient": q["sufficient"], "sections": q["sections"],
                    "level": q["level"], "lab_timeliness": q["lab_timeliness"],
                    "hours_of_data": q["hours_of_data"],
                    "max_stale_hours": max(q["stale_labs_hours"].values()),
                    "warnings": [w for w in q["warnings"] if w["severity"] == "warning"]})
    out.sort(key=lambda r: r["overall_score"])
    levels: dict[str, int] = {}
    for r in out:
        levels[r["level"]] = levels.get(r["level"], 0) + 1
    return {"patients": out, "levels": levels,
            "patients_with_warnings": sum(1 for r in out if r["warnings"])}


@app.get("/api/models")
def models_info(user: User = Depends(require_permission("models.view"))):
    rep = load_report()
    return {"trained_at": rep["trained_at"], "dataset": rep["dataset"],
            "tasks": {t: {"best_model": v["best_model"], "classes": v["classes"]}
                      for t, v in rep["tasks"].items()}}


@app.get("/api/model-performance")
def model_performance(db: Session = Depends(get_db),
                      user: User = Depends(require_permission("models.evaluate"))):
    rep = load_report()
    imp = load_global_importance()
    audit.log_event(db, user, "models.analysis_view", throttle=True)
    return {"report": rep["tasks"], "global_importance": imp,
            "trained_at": rep["trained_at"], "dataset": rep["dataset"]}


@app.get("/api/explanations/{pid}")
def explanations(pid: str = PID, task: str = Query("sepsis_state"),
                 db: Session = Depends(get_db),
                 user: User = Depends(require_permission("explainability.view"))):
    if task not in TASK_ORDER:
        raise HTTPException(400, f"task must be one of {TASK_ORDER}")
    p = _get_patient(db, pid)
    feats = compute_features_for_patient(
        _vit_df(db, pid), {"patient_id": pid, "age": p.age, "sex": p.sex}, abx_frame(db, pid))
    result = explain_prediction(feats.iloc[[-1]], task)
    result["disclaimer"] = DISCLAIMER
    return result


# ---------- role dashboards ----------

@app.get("/api/dashboard/clinician")
def dashboard_clinician(db: Session = Depends(get_db),
                        user: User = Depends(require_permission("patients.monitor"))):
    return clinician_dashboard(db, _patient_rows(db))


@app.get("/api/dashboard/researcher")
def dashboard_researcher(db: Session = Depends(get_db),
                         user: User = Depends(require_permission("models.evaluate"))):
    return researcher_dashboard(db, _patient_rows(db))


@app.get("/api/research/trajectories")
def research_trajectories(db: Session = Depends(get_db),
                          user: User = Depends(require_permission("trajectory.view"))):
    return trajectory_analysis(db, _patient_rows(db))


# ---------- scenario simulation ----------

Scenario = Literal["continue", "stable", "improving", "deteriorating"]
assert set(Scenario.__args__) == set(SCENARIO_DRIFT)


class SimTickRequest(BaseModel):
    scenario: Scenario = "continue"
    hours: int = Field(1, ge=1, le=24)


@app.get("/api/sim/scenarios")
def sim_scenarios(user: User = Depends(require_permission("simulation.run"))):
    desc = {"continue": "Continue the current trajectory (random walk around the present severity).",
            "stable": "Pull the patient toward a stable, low-severity state.",
            "improving": "Severity falls a little every hour.",
            "deteriorating": "Severity rises a little every hour."}
    return {"scenarios": [{"key": k, "label": k.capitalize(), "description": desc[k]}
                          for k in ("stable", "improving", "deteriorating", "continue")],
            "max_hours": 24, "mode": "Synthetic Scenario Simulation"}


@app.post("/api/sim/{pid}/tick")
def sim_tick(body: SimTickRequest, pid: str = PID, db: Session = Depends(get_db),
             user: User = Depends(require_permission("simulation.run"))):
    """Advance a patient by `hours` synthetic hours. Each hour runs the whole
    pipeline: new observation -> features -> all 7 models -> risk score ->
    state engine -> alert engine. Returns the state after the last hour."""
    _get_patient(db, pid)
    steps, alerts, result, before = [], [], None, None
    for _ in range(body.hours):
        try:
            result = tick(db, pid, body.scenario, user.username)
        except ValueError as e:
            raise HTTPException(404, str(e))
        if before is None:
            before = result["risk_before"]
        alerts += result["new_alerts"]
        det = result["predictions"].get("deterioration_6h", {}).get("probabilities", {})
        steps.append({"hour": result["hour"], "risk_score": result["risk"]["score"],
                      "risk_level": result["risk"]["level"],
                      "det6_risk": det.get("Deterioration ≤6h"),
                      "state": result["state"]["label"],
                      "recovery": result["predictions"]["recovery"]["predicted_label"],
                      "new_alerts": len(result["new_alerts"])})
    audit.log_event(db, user, "simulation.advance", target=pid,
                    detail=f"scenario={body.scenario}; hours={body.hours}; "
                           f"now hour {result['hour']}; risk {result['risk']['score']}")
    return {**result, "risk_before": before, "new_alerts": alerts,
            "hours_advanced": body.hours, "steps": steps,
            "mode": "Synthetic Scenario Simulation"}
