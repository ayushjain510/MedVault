"""Live monitoring simulation: extends a patient's timeline hour by hour.

Continues the patient's archetype trajectory (or a user-selected scenario),
appends the new hour to the DB, recomputes features, re-runs all five models
and regenerates alerts — a genuine end-to-end pipeline tick.
"""
import sys
import json
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ..config import ML_DIR
from ..database import (Vital, Prediction, Alert, Patient, AntibioticRecord,
                        RiskScore, SimulationEvent)
from ..alerts.engine import generate_alerts, risk_level_alert
from .analytics import trend_series
from .audit import now_iso
from .predictor import load_bundles, TASK_ORDER, compute_features_for_patient
from .risk import compute_risk, sync_risk_scores, _compact
from .state_engine import compute_state

sys.path.insert(0, str(ML_DIR))

SCENARIO_DRIFT = {
    "continue": 0.0,
    "improving": -0.02,
    "deteriorating": 0.03,
    "stable": None,  # pull toward 0.1
}


def _estimate_severity(recent: list[Vital], lactate: float | None = None) -> float:
    """Inverse mapping from observables to latent severity, used ONCE to start
    a simulation from a patient's current condition.

    Each term inverts the forward mapping used in tick() (e.g. lactate =
    1.1 + sev**1.3 * 5.5), averaged over the last few hours to damp noise.
    `lactate` is the most recent MEASURED value — labs are only sampled every
    few hours, so the latest row alone usually has none."""
    def mean(attr):
        vals = [getattr(r, attr) for r in recent if getattr(r, attr) is not None]
        return sum(vals) / len(vals) if vals else None

    hr, mp, rr = mean("heart_rate"), mean("map"), mean("resp_rate")
    terms = []
    if hr is not None: terms.append((0.25, np.clip((hr - 78) / 45, 0, 1)))
    if mp is not None: terms.append((0.25, np.clip((90 - mp) / 27.3, 0, 1)))
    if lactate is not None: terms.append((0.3, np.clip((lactate - 1.1) / 5.5, 0, 1) ** (1 / 1.3)))
    if rr is not None: terms.append((0.2, np.clip((rr - 15) / 13, 0, 1)))
    if not terms:
        return 0.1
    return float(np.clip(sum(w * v for w, v in terms) / sum(w for w, _ in terms), 0, 1))


def _last_known(db: Session, patient_id: str, column) -> float | None:
    row = (db.query(column).filter(Vital.patient_id == patient_id, column.isnot(None))
           .order_by(Vital.hour.desc()).first())
    return row[0] if row else None


def tick(db: Session, patient_id: str, scenario: str = "continue",
         username: str | None = None) -> dict:
    pat = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if pat is None:
        raise ValueError("unknown patient")
    last = (db.query(Vital).filter(Vital.patient_id == patient_id)
            .order_by(Vital.hour.desc()).first())
    rng = np.random.default_rng()
    if last is None:
        raise ValueError("patient has no observations")
    # The latent severity is simulation STATE: estimated from the record on the
    # first simulated hour, then carried forward in simulation_events. (Re-
    # estimating it from the noisy observables every hour loses more than the
    # scenario drift adds, so a "deteriorating" patient would never deteriorate.)
    # It is never a model input.
    prev_sim = (db.query(SimulationEvent).filter(SimulationEvent.patient_id == patient_id)
                .order_by(SimulationEvent.hour.desc()).first())
    if prev_sim is not None and prev_sim.severity is not None and prev_sim.hour == last.hour:
        sev = prev_sim.severity
    else:
        recent = (db.query(Vital).filter(Vital.patient_id == patient_id)
                  .order_by(Vital.hour.desc()).limit(3).all())
        sev = _estimate_severity(recent, _last_known(db, patient_id, Vital.lactate))
    last_creat = _last_known(db, patient_id, Vital.creatinine) or 0.9
    last_plt = _last_known(db, patient_id, Vital.platelets) or 260
    prev_risk = (db.query(RiskScore).filter(RiskScore.patient_id == patient_id)
                 .order_by(RiskScore.hour.desc()).first())
    drift = SCENARIO_DRIFT.get(scenario, 0.0)
    if drift is None:
        sev = float(np.clip(sev + (0.1 - sev) * 0.15 + rng.normal(0, 0.008), 0, 1))
    else:
        sev = float(np.clip(sev + drift + rng.normal(0, 0.015), 0, 1))

    hour = last.hour + 1
    n = lambda s: rng.normal(0, s)
    hr = 78 + sev * 45 + n(2.5)
    sbp = 122 - sev * 38 + n(4)
    dbp = 74 - sev * 22 + n(3)
    new = Vital(
        patient_id=patient_id, hour=hour,
        heart_rate=round(hr, 1), sbp=round(sbp, 1), dbp=round(dbp, 1),
        map=round(dbp + (sbp - dbp) / 3, 1),
        resp_rate=round(15 + sev * 13 + n(1.2), 1),
        spo2=round(float(np.clip(97.5 - sev * 7 + n(0.6), 78, 100)), 1),
        temperature=round(36.9 + sev * 2.4 + n(0.15), 2),
        lactate=round(float(np.clip(1.1 + sev**1.3 * 5.5 + n(0.2), 0.4, 15)), 2) if hour % 4 == 0 else None,
        wbc=round(float(np.clip(7.5 + sev * 12 + n(0.8), 1, 40)), 2) if hour % 6 == 0 else None,
        creatinine=round(float(np.clip(last_creat + sev * 0.01 + n(0.02), 0.4, 8)), 2) if hour % 6 == 0 else None,
        bilirubin=round(float(np.clip(0.7 + sev * 2.2 + n(0.1), 0.2, 12)), 2) if hour % 8 == 0 else None,
        platelets=round(float(np.clip(last_plt - sev * 2 + n(4), 15, 500))) if hour % 8 == 0 else None,
        urine_output=round(float(np.clip(70 * (1 - sev * 0.75) + n(5), 0, 200)), 1),
        fluid_input=round(80 + sev * 260 + abs(n(15)), 1),
        fluid_output=round(float(np.clip(70 * (1 - sev * 0.75) + n(5), 0, 200)) + 20 + abs(n(8)), 1),
    )
    db.add(new)
    db.add(SimulationEvent(patient_id=patient_id, hour=hour, scenario=scenario,
                           severity=round(sev, 4), username=username or "system", created_at=now_iso()))
    pat.n_hours = hour + 1
    db.commit()

    # Recompute pipeline on the full (updated) history
    rows = (db.query(Vital).filter(Vital.patient_id == patient_id)
            .order_by(Vital.hour).all())
    vit_df = pd.DataFrame([{c: getattr(r, c) for c in
                            ["patient_id", "hour", "heart_rate", "sbp", "dbp", "map",
                             "resp_rate", "spo2", "temperature", "lactate", "wbc",
                             "creatinine", "bilirubin", "platelets", "urine_output",
                             "fluid_input", "fluid_output"]} for r in rows])
    ab = db.query(AntibioticRecord).filter(AntibioticRecord.patient_id == patient_id).all()
    ab_df = pd.DataFrame([{"patient_id": a.patient_id, "start_hour": a.start_hour}
                          for a in ab]) if ab else pd.DataFrame(columns=["patient_id", "start_hour"])
    feats = compute_features_for_patient(
        vit_df, {"patient_id": patient_id, "age": pat.age, "sex": pat.sex}, ab_df)
    feat_row = feats.iloc[[-1]]

    bundles = load_bundles()
    preds = {}
    for task in TASK_ORDER:
        b = bundles[task]
        X = feat_row[b["feature_columns"]].values
        proba = b["model"].predict_proba(X)[0]
        model_classes = list(b["model"].classes_)
        cls_pos = int(np.argmax(proba))
        idx = int(model_classes[cls_pos])
        probs = {b["classes"][int(model_classes[j])]: round(float(p), 4)
                 for j, p in enumerate(proba)}
        preds[task] = {"predicted_class": idx, "predicted_label": b["classes"][idx],
                       "probability": round(float(proba[cls_pos]), 4),
                       "probabilities": probs, "model": b["model_name"]}
        db.add(Prediction(patient_id=patient_id, hour=hour, task=task,
                          predicted_class=idx, predicted_label=b["classes"][idx],
                          probability=preds[task]["probability"],
                          probabilities_json=json.dumps(probs)))

    # Composite risk for the new hour — same function that serves the risk API.
    sync_risk_scores(db, patient_id, commit=False)       # backfill if never computed
    trend = float(trend_series(vit_df)[-1])
    risk = compute_risk(preds, hour + 1, trend)
    db.query(RiskScore).filter(RiskScore.patient_id == patient_id,
                               RiskScore.hour == hour).delete()
    db.add(RiskScore(patient_id=patient_id, hour=hour, score=risk["score"],
                     level=risk["level"], components_json=_compact(risk)))

    new_alerts = generate_alerts(patient_id, hour, feat_row.iloc[0], preds)
    escalation = risk_level_alert(patient_id, hour, risk,
                                  prev_risk.level if prev_risk else None,
                                  prev_risk.score if prev_risk else None)
    # cooldown: a score hovering on a band edge must not re-alert every hour
    if escalation and not (db.query(Alert.id).filter(
            Alert.patient_id == patient_id, Alert.title == escalation["title"],
            Alert.hour >= hour - 6).first()):
        new_alerts.append(escalation)
    for a in new_alerts:
        db.add(Alert(**a))
    db.commit()

    return {"hour": hour, "vitals": {c: getattr(new, c) for c in
            ["heart_rate", "sbp", "dbp", "map", "resp_rate", "spo2", "temperature",
             "lactate", "wbc", "urine_output", "fluid_input", "fluid_output"]},
            "predictions": preds, "new_alerts": new_alerts,
            "scenario": scenario, "simulated": True,
            "risk": {"score": risk["score"], "level": risk["level"]},
            "risk_before": ({"score": prev_risk.score, "level": prev_risk.level}
                            if prev_risk else None),
            "state": compute_state(preds, hour + 1)}
