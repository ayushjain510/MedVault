"""Shared read helpers: one place that turns stored rows into the frames and
dicts the services (risk, timeline, analytics, explanations) work on."""
import json

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import Vital, Prediction, AntibioticRecord

VITAL_FIELDS = ["heart_rate", "sbp", "dbp", "map", "resp_rate", "spo2", "temperature"]
LAB_FIELDS = ["lactate", "wbc", "creatinine", "bilirubin", "platelets"]
FLUID_FIELDS = ["urine_output", "fluid_input", "fluid_output"]
ALL_FIELDS = ["patient_id", "hour"] + VITAL_FIELDS + LAB_FIELDS + FLUID_FIELDS


def _pred_dict(r: Prediction) -> dict:
    return {"predicted_class": r.predicted_class, "predicted_label": r.predicted_label,
            "probability": r.probability, "probabilities": json.loads(r.probabilities_json)}


def latest_predictions(db: Session, pid: str) -> dict:
    max_hour = (db.query(func.max(Prediction.hour))
                .filter(Prediction.patient_id == pid).scalar())
    rows = (db.query(Prediction)
            .filter(Prediction.patient_id == pid, Prediction.hour == max_hour).all())
    return {r.task: _pred_dict(r) for r in rows}


def predictions_by_hour(db: Session, pid: str) -> dict[int, dict]:
    """{hour: {task: prediction}} for the whole stay, hours ascending."""
    out: dict[int, dict] = {}
    for r in (db.query(Prediction).filter(Prediction.patient_id == pid)
              .order_by(Prediction.hour).all()):
        out.setdefault(r.hour, {})[r.task] = _pred_dict(r)
    return out


def vitals_frame(db: Session, pid: str) -> pd.DataFrame:
    """All observations of a patient, hours ascending. Empty frame if none."""
    rows = db.query(Vital).filter(Vital.patient_id == pid).order_by(Vital.hour).all()
    return pd.DataFrame([{c: getattr(r, c) for c in ALL_FIELDS} for r in rows],
                        columns=ALL_FIELDS)


def abx_frame(db: Session, pid: str) -> pd.DataFrame:
    ab = db.query(AntibioticRecord).filter(AntibioticRecord.patient_id == pid).all()
    return pd.DataFrame([{"patient_id": a.patient_id, "start_hour": a.start_hour} for a in ab],
                        columns=["patient_id", "start_hour"])
