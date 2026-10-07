"""MedVault Composite Risk Score — a transparent 0-100 summary of the existing
model outputs. Research / prototype indicator, NOT a validated clinical score.

It adds no new model. Six components, each derived from something the pipeline
already produces, contribute a fixed maximum number of points (sum = 100):

  deterioration        35  0.5*p(6h) + 0.3*p(12h) + 0.2*p(24h)
  sepsis_state         20  probability-weighted severity of the 8-state classifier
  recovery             20  100 - recovery score (state_engine.RECOVERY_WEIGHTS)
  antibiotic_response  10  probability mass on unfavourable AR classes
  fluid_status          8  probability mass on unfavourable FS classes
  trend                 7  unfavourable share of the 6h-vs-previous-6h deltas
                           (the "What changed?" analysis)

Every component uses the model's full probability distribution rather than
the arg-max label, so the score moves smoothly instead of jumping when a
prediction flips class. A component whose input is missing is left out and
the remaining ones are renormalised — the endpoint never fails on a missing
prediction. Below 6 h of data no score is produced at all.

One rule ties the score to the state engine: a patient the rule-based engine
classifies STATE 7 (High-Risk Clinical Trajectory) is never shown below the
HIGH band (see ENGINE_FLOOR). When the floor is used the response says so and
still reports the unadjusted raw score.
"""
import json
import math

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import Patient, RiskScore, Alert, AntibioticRecord
from .analytics import data_quality, trend_series
from .patient_data import latest_predictions, predictions_by_hour, vitals_frame
from .state_engine import (compute_state, RECOVERY_WEIGHTS, ABX_WEIGHTS, FLUID_WEIGHTS)

LABEL = "MedVault Composite Risk Score"
NOTE = "Research / prototype indicator — not a validated clinical score."

BANDS = [(75, "CRITICAL"), (50, "HIGH"), (25, "MODERATE"), (0, "LOW")]
INSUFFICIENT = "INSUFFICIENT DATA"
LEVEL_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
ENGINE_FLOOR = 50        # minimum score while the state engine reports STATE 7
MIN_HOURS = 6

MAX_POINTS = {"deterioration": 35, "sepsis_state": 20, "recovery": 20,
              "antibiotic_response": 10, "fluid_status": 8, "trend": 7}
COMPONENT_LABELS = {"deterioration": "Deterioration risk (6/12/24h)",
                    "sepsis_state": "Sepsis state",
                    "recovery": "Recovery trajectory",
                    "antibiotic_response": "Antibiotic response",
                    "fluid_status": "Fluid status",
                    "trend": "Recent physiological trend"}
DET_HORIZON_WEIGHTS = {"deterioration_6h": 0.5, "deterioration_12h": 0.3, "deterioration_24h": 0.2}

# Severity (0 = no concern, 1 = maximum) of each sepsis-state class.
SEPSIS_SEVERITY = {"Stable": 0.0, "At Risk": 0.35, "Active Sepsis": 0.6,
                   "Severe/Deteriorating": 0.9, "Treatment Response": 0.35,
                   "Recovery": 0.1, "Non-responding": 0.8, "Escalation": 1.0}
TREND_FULL_SCALE = 3.0   # an unfavourable what-changed score of -3 = full trend points


def level_for(score: int | None) -> str:
    if score is None:
        return INSUFFICIENT
    return next(name for floor, name in BANDS if score >= floor)


def _p_det(pred: dict | None) -> float | None:
    if not pred:
        return None
    for k, v in pred.get("probabilities", {}).items():
        if k.startswith("Deterioration"):
            return float(v)
    return None


def _unfavourable(pred: dict | None, weights: list[float]) -> float | None:
    """1 - probability-weighted favourability; class order = training order."""
    if not pred or not pred.get("probabilities"):
        return None
    fav = sum(p * (weights[i] if i < len(weights) else 0.0)
              for i, p in enumerate(pred["probabilities"].values()))
    return float(min(max(1 - fav, 0.0), 1.0))


def _component(key, fraction, value, detail):
    mx = MAX_POINTS[key]
    if fraction is None:
        return {"key": key, "label": COMPONENT_LABELS[key], "available": False,
                "points": None, "max_points": mx, "fraction": None,
                "value": "not available", "detail": detail, "concern": "unknown"}
    pts = round(fraction * mx, 1)
    return {"key": key, "label": COMPONENT_LABELS[key], "available": True,
            "points": pts, "max_points": mx, "fraction": round(fraction, 3),
            "value": value, "detail": detail,
            "concern": "high" if fraction >= 0.6 else "moderate" if fraction >= 0.3 else "low"}


def compute_risk(preds: dict, hours_of_data: int, trend_score: float | None = None) -> dict:
    """Pure function: model outputs (+ optional trend score) -> risk dict."""
    if hours_of_data < MIN_HOURS:
        return {"score": None, "level": INSUFFICIENT, "components": [], "floor_applied": False,
                "raw_score": None,
                "reason": f"Only {hours_of_data}h of observations; at least {MIN_HOURS}h are required."}

    comps = []

    probs = {t: _p_det(preds.get(t)) for t in DET_HORIZON_WEIGHTS}
    avail = {t: p for t, p in probs.items() if p is not None}
    if avail:
        w = sum(DET_HORIZON_WEIGHTS[t] for t in avail)
        blended = sum(p * DET_HORIZON_WEIGHTS[t] for t, p in avail.items()) / w
        value = " · ".join(f"{t.split('_')[1]} {p:.0%}" for t, p in avail.items())
        comps.append(_component("deterioration", blended, value,
                                "Blend of the three deterioration models, weighted 0.5 / 0.3 / 0.2."))
    else:
        comps.append(_component("deterioration", None, None, "No deterioration prediction stored."))

    ss = preds.get("sepsis_state")
    if ss and ss.get("probabilities"):
        frac = sum(p * SEPSIS_SEVERITY.get(c, 0.5) for c, p in ss["probabilities"].items())
        comps.append(_component("sepsis_state", min(frac, 1.0), ss["predicted_label"],
                                "Probability-weighted severity of the sepsis-state classifier."))
    else:
        comps.append(_component("sepsis_state", None, None, "No sepsis-state prediction stored."))

    for key, weights, what in (
            ("recovery", RECOVERY_WEIGHTS, "recovery-trajectory"),
            ("antibiotic_response", ABX_WEIGHTS, "antibiotic-response"),
            ("fluid_status", FLUID_WEIGHTS, "fluid-status")):
        pred = preds.get(key)
        frac = _unfavourable(pred, weights)
        comps.append(_component(key, frac, pred["predicted_label"] if pred else None,
                                f"Probability mass on unfavourable {what} classes."))

    if trend_score is None or (isinstance(trend_score, float) and math.isnan(trend_score)):
        comps.append(_component("trend", None, None,
                                "Needs 12h of observations (last 6h vs the previous 6h)."))
    else:
        frac = min(max(-trend_score / TREND_FULL_SCALE, 0.0), 1.0)
        value = ("Worsening" if trend_score < -1 else "Improving" if trend_score > 1
                 else "Mixed / stable")
        comps.append(_component("trend", frac, value,
                                "Unfavourable share of the last-6h vs previous-6h changes in "
                                "vitals and labs."))

    used = [c for c in comps if c["available"]]
    if not used:
        return {"score": None, "level": INSUFFICIENT, "components": comps, "floor_applied": False,
                "raw_score": None, "reason": "No model outputs are available for this patient."}
    raw = round(100 * sum(c["points"] for c in used) / sum(c["max_points"] for c in used))

    engine = compute_state(preds, hours_of_data)
    floor = engine.get("state") == 7 and raw < ENGINE_FLOOR
    score = ENGINE_FLOOR if floor else raw
    comps.sort(key=lambda c: -(c["points"] if c["points"] is not None else -1))
    return {"score": int(score), "level": level_for(score), "components": comps,
            "raw_score": int(raw), "floor_applied": bool(floor),
            "engine_state": engine["label"],
            "renormalised": len(used) < len(comps)}


def _compact(risk: dict) -> str:
    return json.dumps([{"key": c["key"], "label": c["label"], "points": c["points"],
                        "max_points": c["max_points"], "value": c["value"]}
                       for c in risk["components"]])


def risk_history(db: Session, pid: str) -> list[dict]:
    """Risk at every hour that has stored predictions (causal at each hour)."""
    by_hour = predictions_by_hour(db, pid)
    if not by_hour:
        return []
    vit = vitals_frame(db, pid)
    trend = dict(zip(vit["hour"].tolist(), trend_series(vit).tolist())) if len(vit) else {}
    return [{"hour": h, **compute_risk(preds, h + 1, trend.get(h))}
            for h, preds in by_hour.items()]


def sync_risk_scores(db: Session, pid: str, commit: bool = True) -> int:
    """Persist any missing hours of risk history for one patient."""
    have = {h for (h,) in db.query(RiskScore.hour).filter(RiskScore.patient_id == pid)}
    n = 0
    for r in risk_history(db, pid):
        if r["hour"] in have:
            continue
        db.add(RiskScore(patient_id=pid, hour=r["hour"], score=r["score"],
                         level=r["level"], components_json=_compact(r)))
        n += 1
    if n and commit:
        db.commit()
    return n


def ensure_risk_scores(db: Session) -> None:
    """Backfill patients that have no stored risk (database seeded before the
    risk score existed). No-op once every patient has rows."""
    have = {p for (p,) in db.query(RiskScore.patient_id).distinct()}
    missing = [p for (p,) in db.query(Patient.patient_id) if p not in have]
    for pid in missing:
        sync_risk_scores(db, pid, commit=False)
    if missing:
        db.commit()


def _latest_hours(db: Session):
    return (db.query(RiskScore.patient_id, func.max(RiskScore.hour).label("h"))
            .group_by(RiskScore.patient_id).subquery())


def latest_risk_map(db: Session) -> dict[str, RiskScore]:
    ensure_risk_scores(db)
    sub = _latest_hours(db)
    rows = (db.query(RiskScore)
            .join(sub, (RiskScore.patient_id == sub.c.patient_id) & (RiskScore.hour == sub.c.h)).all())
    return {r.patient_id: r for r in rows}


def risk_at_offset(db: Session, hours_back: int = 6) -> dict[str, int | None]:
    """Score `hours_back` hours before each patient's latest hour."""
    sub = _latest_hours(db)
    rows = (db.query(RiskScore.patient_id, RiskScore.score)
            .join(sub, (RiskScore.patient_id == sub.c.patient_id)
                  & (RiskScore.hour == sub.c.h - hours_back)).all())
    return {pid: score for pid, score in rows}


def _quality_caveat(dq: dict) -> dict:
    warnings = [w for w in dq["warnings"] if w["severity"] == "warning"]
    caution = dq["level"] != "GOOD" or bool(warnings)
    if not caution:
        text = "Data completeness is adequate for the inputs behind this score."
    else:
        reasons = [w["title"].rstrip(".") for w in warnings[:2]]
        reasons = [r[0].lower() + r[1:] if not r[:3].isupper() else r for r in reasons]
        if not reasons:
            reasons = [f"overall data quality is {dq['overall_score']}%"]
        text = ("Risk prediction should be interpreted with caution because "
                + " and ".join(reasons) + ".")
    return {"overall_score": dq["overall_score"], "level": dq["level"], "caution": caution,
            "interpretation": text,
            "score_adjusted": False}   # the score itself is never altered by data quality


def patient_risk(db: Session, patient: Patient) -> dict:
    """Full risk payload for GET /api/patients/{id}/risk (computed live)."""
    pid = patient.patient_id
    preds = latest_predictions(db, pid)
    vit = vitals_frame(db, pid)
    ts = trend_series(vit) if len(vit) else np.array([])
    trend = float(ts[-1]) if len(ts) else None
    risk = compute_risk(preds, patient.n_hours, trend)

    sync_risk_scores(db, pid)
    hist = (db.query(RiskScore.hour, RiskScore.score, RiskScore.level)
            .filter(RiskScore.patient_id == pid).order_by(RiskScore.hour).all())
    series = [{"hour": h, "score": s, "level": lv} for h, s, lv in hist]
    current_hour = patient.n_hours - 1
    prev = next((r["score"] for r in series if r["hour"] == current_hour - 6), None)
    delta = risk["score"] - prev if risk["score"] is not None and prev is not None else None

    has_abx = db.query(AntibioticRecord).filter(AntibioticRecord.patient_id == pid).count() > 0
    dq = data_quality(vit, has_abx) if len(vit) else None
    sevs = [s for (s,) in db.query(Alert.severity)
            .filter(Alert.patient_id == pid, Alert.hour == current_hour)]
    top_alert = next((lv for lv in ("critical", "high", "moderate", "info") if lv in sevs), "none")

    return {"patient_id": pid, "hour": current_hour, **risk,
            "label": LABEL, "note": NOTE,
            "bands": [{"level": name, "min": floor} for floor, name in reversed(BANDS)],
            "previous_score_6h": prev, "delta_6h": delta, "history": series,
            "active_alert_level": top_alert,
            "data_quality": _quality_caveat(dq) if dq else None,
            "updated_at_hour": current_hour}
