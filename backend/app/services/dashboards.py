"""Role-specific dashboard payloads and system-health checks.

Three services over the same data:
  clinician   who needs attention now
  researcher  how the models and the dataset behave
  admin       is the platform healthy and who is using it
Every number is read from the database, the model report or a live check.
"""
import json
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..config import (DATABASE_URL, JWT_SECRET_IS_DEFAULT, JWT_EXPIRE_MINUTES,
                      JWT_ALGORITHM, MODELS_DIR)
from ..database import (Patient, Vital, Prediction, Alert, User, AuditLog,
                        RiskScore, SimulationEvent)
from . import audit
from .analytics import VITALS, LABS, FLUIDS
from .permissions import ROLES
from .predictor import load_bundles, load_report, TASK_ORDER
from .risk import BANDS, INSUFFICIENT, MAX_POINTS, risk_at_offset, latest_risk_map

STARTED_AT = time.time()
RISK_LEVELS = [name for _, name in reversed(BANDS)] + [INSUFFICIENT]


def risk_level_counts(rows: list[dict]) -> dict:
    counts = {lv: 0 for lv in RISK_LEVELS}
    for r in rows:
        counts[r.get("risk_level") or INSUFFICIENT] = counts.get(r.get("risk_level") or INSUFFICIENT, 0) + 1
    return counts


def active_alerts(db: Session) -> list[Alert]:
    """Alerts raised at each patient's CURRENT hour (older ones are history)."""
    return (db.query(Alert).join(Patient, Patient.patient_id == Alert.patient_id)
            .filter(Alert.hour == Patient.n_hours - 1).all())


def _top_contributor(row: RiskScore | None) -> dict | None:
    if row is None or not row.components_json:
        return None
    comps = [c for c in json.loads(row.components_json) if c.get("points")]
    return max(comps, key=lambda c: c["points"]) if comps else None


def risk_ranking(db: Session, patient_rows: list[dict]) -> list[dict]:
    """Every patient with score, 6h change and largest contributor, highest first."""
    latest = latest_risk_map(db)
    before = risk_at_offset(db, 6)
    out = []
    for p in patient_rows:
        pid = p["patient_id"]
        prev = before.get(pid)
        score = p.get("risk_score")
        top = _top_contributor(latest.get(pid))
        out.append({
            "patient_id": pid, "age": p["age"], "sex": p["sex"], "last_hour": p["last_hour"],
            "risk_score": score, "risk_level": p.get("risk_level"),
            "previous_score_6h": prev,
            "delta_6h": score - prev if score is not None and prev is not None else None,
            "top_contributor": ({"label": top["label"], "value": top["value"],
                                 "points": top["points"], "max_points": top["max_points"]}
                                if top else None),
            "components": json.loads(latest[pid].components_json) if pid in latest else [],
            "engine_state": p["engine_state"], "recovery": p["recovery"],
            "det6_risk": p["det6_risk"], "alert_level": p["alert_level"]})
    out.sort(key=lambda r: -(r["risk_score"] if r["risk_score"] is not None else -1))
    return out


def clinician_dashboard(db: Session, patient_rows: list[dict]) -> dict:
    ranking = risk_ranking(db, patient_rows)
    levels = risk_level_counts(patient_rows)
    act = active_alerts(db)
    sev = {s: sum(1 for a in act if a.severity == s) for s in ("critical", "high", "moderate", "info")}
    changed = [r for r in ranking if r["delta_6h"] is not None and abs(r["delta_6h"]) >= 5]
    changed.sort(key=lambda r: -abs(r["delta_6h"]))
    order = {"critical": 0, "high": 1, "moderate": 2, "info": 3}
    urgent = sorted((a for a in act if a.severity in ("critical", "high") and not a.acknowledged),
                    key=lambda a: (order[a.severity], -a.id))[:8]
    return {
        "total_patients": len(patient_rows),
        "risk_levels": levels,
        "high_risk_patients": levels["HIGH"],
        "critical_patients": levels["CRITICAL"],
        "active_alerts": {**sev, "total": len(act),
                          "unacknowledged": sum(1 for a in act if not a.acknowledged
                                                and a.severity in ("critical", "high"))},
        "improving": sum(1 for p in patient_rows if (p["recovery"] or "").startswith("RT-0")),
        "top_risk": ranking[:8],
        "recent_changes": changed[:8],
        "urgent_alerts": [{"id": a.id, "patient_id": a.patient_id, "hour": a.hour,
                           "severity": a.severity, "category": a.category, "title": a.title}
                          for a in urgent],
    }


def dataset_completeness(db: Session) -> dict:
    """Unit-wide completeness per section — the same definition as the
    per-patient data-quality sections (share of non-missing values)."""
    total = db.query(func.count(Vital.id)).scalar() or 0
    if not total:
        return {"vitals": None, "laboratory": None, "fluid_records": None}
    counts = db.query(*[func.count(getattr(Vital, c)) for c in VITALS + LABS + FLUIDS]).one()
    by_col = dict(zip(VITALS + LABS + FLUIDS, counts))

    def pct(cols):
        return round(100 * sum(by_col[c] for c in cols) / (total * len(cols)), 1)
    return {"vitals": pct(VITALS), "laboratory": pct(LABS), "fluid_records": pct(FLUIDS)}


def _task_rows() -> list[dict]:
    rep = load_report()
    rows = []
    for task, t in rep["tasks"].items():
        best = t["best_model"]
        val, test = t["models"][best]["val"], t["models"][best]["test"]
        rows.append({"task": task, "best_model": best, "n_classes": len(t["classes"]),
                     "candidates": list(t["models"]),
                     "val_f1_macro": val["f1_macro"], "val_recall_macro": val["recall_macro"],
                     "test_f1_macro": test["f1_macro"], "test_recall_macro": test["recall_macro"],
                     "test_roc_auc": test.get("roc_auc")})
    return rows


def researcher_dashboard(db: Session, patient_rows: list[dict]) -> dict:
    rep = load_report()
    tasks = _task_rows()
    recovery = {}
    for p in patient_rows:
        key = p["recovery"] or "—"
        recovery[key] = recovery.get(key, 0) + 1
    archetypes = dict(db.query(Patient.archetype, func.count(Patient.patient_id))
                      .group_by(Patient.archetype).all())
    scores = [p["risk_score"] for p in patient_rows if p.get("risk_score") is not None]
    return {
        "n_patients": len(patient_rows),
        "n_observations": db.query(func.count(Vital.id)).scalar() or 0,
        "n_predictions": db.query(func.count(Prediction.id)).scalar() or 0,
        "n_simulated_hours": db.query(func.count(SimulationEvent.id)).scalar() or 0,
        "n_features": len(rep.get("feature_columns", [])),
        "prediction_tasks": tasks,
        "n_prediction_tasks": len(tasks),
        "models_available": len(tasks),
        "candidate_algorithms": sorted({c for t in tasks for c in t["candidates"]}),
        "n_models_evaluated": sum(len(t["candidates"]) for t in tasks),
        "mean_val_f1_macro": round(sum(t["val_f1_macro"] for t in tasks) / len(tasks), 3),
        "dataset": rep["dataset"], "trained_at": rep["trained_at"],
        "model_version": rep.get("model_version"), "feature_version": rep.get("feature_version"),
        "splits": {k: len(v) for k, v in rep.get("splits", {}).items()},
        "data_completeness": dataset_completeness(db),
        "risk_levels": risk_level_counts(patient_rows),
        "mean_risk_score": round(sum(scores) / len(scores), 1) if scores else None,
        "recovery_distribution": dict(sorted(recovery.items())),
        "archetypes": archetypes,
    }


def trajectory_analysis(db: Session, patient_rows: list[dict]) -> dict:
    """Cohort view: how the composite risk evolves per simulator archetype.
    Archetype is simulator ground truth, which is why this is research-only."""
    arch = dict(db.query(Patient.patient_id, Patient.archetype).all())
    sums: dict[tuple[str, int], list[int]] = {}
    rows = (db.query(RiskScore.patient_id, RiskScore.hour, RiskScore.score)
            .filter(RiskScore.score.isnot(None)).all())
    for pid, hour, score in rows:
        key = (arch.get(pid, "unknown"), hour // 6 * 6)
        acc = sums.setdefault(key, [0, 0])
        acc[0] += score
        acc[1] += 1
    archetypes = sorted({a for a, _ in sums})
    buckets = sorted({h for _, h in sums})
    series = []
    for h in buckets:
        point = {"hour": h}
        for a in archetypes:
            if (a, h) in sums and sums[(a, h)][1] >= 5:   # skip thin buckets
                point[a] = round(sums[(a, h)][0] / sums[(a, h)][1], 1)
        series.append(point)

    per_arch = {}
    for p in patient_rows:
        a = arch.get(p["patient_id"], "unknown")
        d = per_arch.setdefault(a, {"archetype": a, "n": 0, "scores": [], "levels": {},
                                    "recovery": {}})
        d["n"] += 1
        if p.get("risk_score") is not None:
            d["scores"].append(p["risk_score"])
        lv = p.get("risk_level") or INSUFFICIENT
        d["levels"][lv] = d["levels"].get(lv, 0) + 1
        rec = (p["recovery"] or "—").split(" ")[0]
        d["recovery"][rec] = d["recovery"].get(rec, 0) + 1
    summary = []
    for a in sorted(per_arch):
        d = per_arch[a]
        sc = d.pop("scores")
        d["mean_risk"] = round(sum(sc) / len(sc), 1) if sc else None
        d["min_risk"], d["max_risk"] = (min(sc), max(sc)) if sc else (None, None)
        summary.append(d)
    return {"archetypes": archetypes, "bucket_hours": 6, "risk_over_time": series,
            "summary": summary, "risk_levels": RISK_LEVELS,
            "note": ("Mean MedVault Composite Risk Score per 6-hour bucket, grouped by the "
                     "synthetic generator's archetype (ground truth the models never see). "
                     "Buckets with fewer than 5 patient-hours are omitted.")}


def system_health(db: Session) -> dict:
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_status = {"status": "ok", "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
    except Exception as e:  # noqa: BLE001 — health check must report, not raise
        db_status = {"status": "down", "error": type(e).__name__}
    db_status["dialect"] = DATABASE_URL.split(":", 1)[0]

    models = []
    try:
        bundles = load_bundles()
    except Exception as e:  # noqa: BLE001
        bundles, load_error = {}, f"{type(e).__name__}: model files could not be loaded"
    else:
        load_error = None
    for task in TASK_ORDER:
        b = bundles.get(task)
        models.append({"task": task, "loaded": b is not None,
                       "file_present": (MODELS_DIR / f"{task}.pkl").exists(),
                       "algorithm": b["model_name"] if b else None,
                       "model_version": b.get("model_version") if b else None,
                       "feature_version": b.get("feature_version") if b else None,
                       "n_features": len(b["feature_columns"]) if b else None,
                       "trained_at": b.get("trained_at") if b else None})
    loaded = sum(1 for m in models if m["loaded"])
    model_status = {"status": "ok" if loaded == len(TASK_ORDER) else "degraded" if loaded else "down",
                    "loaded": loaded, "expected": len(TASK_ORDER), "error": load_error}

    counts = {"patients": db.query(func.count(Patient.patient_id)).scalar(),
              "observations": db.query(func.count(Vital.id)).scalar(),
              "predictions": db.query(func.count(Prediction.id)).scalar(),
              "alerts": db.query(func.count(Alert.id)).scalar(),
              "risk_scores": db.query(func.count(RiskScore.id)).scalar(),
              "simulated_hours": db.query(func.count(SimulationEvent.id)).scalar(),
              "users": db.query(func.count(User.id)).scalar(),
              "audit_events": db.query(func.count(AuditLog.id)).scalar()}
    ok = db_status["status"] == "ok" and model_status["status"] == "ok"
    return {"status": "ok" if ok else "degraded",
            "api": {"status": "ok", "uptime_seconds": round(time.time() - STARTED_AT)},
            "database": db_status, "model_service": model_status, "models": models,
            "counts": counts,
            "security": {"jwt_secret_is_default": JWT_SECRET_IS_DEFAULT},
            "data": "synthetic", "checked_at": audit.now_iso()}


def admin_dashboard(db: Session) -> dict:
    users = db.query(User).all()
    by_role = {r: sum(1 for u in users if u.role == r) for r in ROLES}
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    recent = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(10).all()
    health = system_health(db)
    return {
        "users": {"total": len(users), "active": sum(1 for u in users if u.is_active),
                  "inactive": sum(1 for u in users if not u.is_active), "by_role": by_role},
        "system": {"status": health["status"], "api": health["api"],
                   "database": health["database"], "model_service": health["model_service"]},
        "security": health["security"],
        "counts": health["counts"],
        "activity_24h": {
            "events": db.query(func.count(AuditLog.id)).filter(AuditLog.timestamp >= since).scalar(),
            "logins": db.query(func.count(AuditLog.id)).filter(
                AuditLog.timestamp >= since, AuditLog.action == "auth.login",
                AuditLog.status == "success").scalar(),
            "failed_logins": db.query(func.count(AuditLog.id)).filter(
                AuditLog.timestamp >= since, AuditLog.action == "auth.login",
                AuditLog.status != "success").scalar(),
            "denied": db.query(func.count(AuditLog.id)).filter(
                AuditLog.timestamp >= since, AuditLog.status == "denied").scalar()},
        "recent_activity": [audit.serialize(r) for r in recent],
    }


def system_settings() -> dict:
    """Read-only view of the effective configuration. Secrets are never returned."""
    from ..config import DISCLAIMER
    from .analytics import QUALITY_BANDS, STALE_LAB_HOURS
    from .simulator import SCENARIO_DRIFT
    rep = load_report()
    return {
        "authentication": {"algorithm": JWT_ALGORITHM, "token_lifetime_minutes": JWT_EXPIRE_MINUTES,
                           "password_hashing": "bcrypt",
                           "jwt_secret_is_default": JWT_SECRET_IS_DEFAULT},
        "database": {"dialect": DATABASE_URL.split(":", 1)[0]},
        "models": {"dataset": rep["dataset"], "trained_at": rep["trained_at"],
                   "model_version": rep.get("model_version"),
                   "feature_version": rep.get("feature_version")},
        "risk_score": {"bands": [{"level": n, "min": f} for f, n in reversed(BANDS)],
                       "max_points": MAX_POINTS, "minimum_hours": 6},
        "data_quality": {"bands": [{"level": n, "min": f} for f, n in reversed(QUALITY_BANDS)],
                         "stale_lab_hours": STALE_LAB_HOURS},
        "simulation": {"scenarios": list(SCENARIO_DRIFT), "max_hours_per_request": 24},
        "disclaimer": DISCLAIMER,
        "editable": False,
        "note": ("Settings are defined in code and environment variables "
                 "(JWT_SECRET, DATABASE_URL, ALLOWED_ORIGINS) and are shown read-only."),
    }
