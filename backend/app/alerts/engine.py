"""Alert generation from model outputs + trend analysis.

Alerts advise clinician review only — they never issue treatment orders.
Rule-based routing on top of ML outputs; deliberately separate from the models.
"""
import pandas as pd

REVIEW = "Recommended: clinician review."


def generate_alerts(pid: str, hour: int, feat_row: pd.Series, preds: dict) -> list[dict]:
    alerts = []

    def add(severity, category, title, message, variable=None, confidence=None):
        alerts.append({"patient_id": pid, "hour": int(hour), "severity": severity,
                       "category": category, "title": title,
                       "message": f"{message} {REVIEW}",
                       "variable": variable, "confidence": confidence})

    if hour < 6:
        add("info", "DATA QUALITY", "Insufficient recent observations for reliable prediction",
            f"Only {hour + 1}h of observations are available; model outputs are withheld "
            "until at least 6h of data exist.")
        return alerts

    det = preds.get("deterioration_6h", {})
    p_det = det.get("probabilities", {}).get("Deterioration ≤6h", 0)
    if p_det >= 0.75:
        add("critical", "HIGH RISK", "Rapid deterioration risk detected",
            f"Model estimates a {p_det:.0%} probability of deterioration within 6 hours.",
            confidence=p_det)
    elif p_det >= 0.5:
        add("high", "HIGH RISK", "Elevated 6-hour deterioration risk",
            f"Model estimates a {p_det:.0%} probability of deterioration within 6 hours.",
            confidence=p_det)

    state = preds.get("sepsis_state", {})
    if state.get("predicted_label") == "Escalation":
        add("critical", "ESCALATION", "High-risk trajectory — urgent assessment suggested",
            "The model detects a trajectory consistent with the need for urgent clinical assessment.",
            confidence=state.get("probability"))
    elif state.get("predicted_label") == "Severe/Deteriorating":
        add("high", "STATE", "Severe / deteriorating pattern",
            "Worsening physiological trends detected by the state classifier.",
            confidence=state.get("probability"))

    if feat_row.get("map_slope_6", 0) < -0.8:
        add("high", "TREND", "MAP has declined over the recent monitoring window",
            f"MAP 6h trend: {feat_row['map_slope_6']:.2f} mmHg/h "
            f"(current {feat_row.get('map_cur', float('nan')):.0f} mmHg).", "map")
    if feat_row.get("lactate_slope_6", 0) > 0.12:
        add("high", "LACTATE", "Lactate trajectory is worsening",
            f"Lactate rising at {feat_row['lactate_slope_6']:.2f} mmol/L per hour "
            f"(current {feat_row.get('lactate_cur', float('nan')):.1f} mmol/L).", "lactate")
    if feat_row.get("creatinine_slope_12", 0) > 0.03:
        add("moderate", "TREND", "Renal-function indicators are worsening over the recent window",
            f"Creatinine rising at {feat_row['creatinine_slope_12']:.3f} mg/dL per hour "
            f"(current {feat_row.get('creatinine_cur', float('nan')):.2f} mg/dL).", "creatinine")

    fl = preds.get("fluid_status", {})
    fl_cls = fl.get("predicted_class")
    if fl_cls == 3:
        add("high", "FLUID", "Significant fluid accumulation concern",
            f"Cumulative balance ~{feat_row.get('cum_fluid_balance', 0):.0f} mL. "
            "Review fluid strategy, urine output and oxygenation.",
            "cum_fluid_balance", fl.get("probability"))
    elif fl_cls == 2:
        add("moderate", "FLUID", "Cumulative positive fluid balance is increasing",
            f"Cumulative balance ~{feat_row.get('cum_fluid_balance', 0):.0f} mL and rising "
            f"({feat_row.get('net_fluid_6h', 0):.0f} mL net over 6h).",
            "cum_fluid_balance", fl.get("probability"))
    elif fl_cls == 4:
        add("high", "FLUID", "Possible inadequate hemodynamic response",
            f"Urine output (6h mean) {feat_row.get('urine_output_mean_6', 0):.0f} mL/h "
            "with concerning haemodynamics.", "urine_output", fl.get("probability"))

    ab = preds.get("antibiotic_response", {})
    if ab.get("predicted_class") in (3, 4):
        add("high", "ANTIBIOTIC RESPONSE", "Observed treatment-response trajectory remains concerning",
            "Expected improvement has not been observed. Review culture data, antimicrobial "
            "coverage, source control and clinical status.", confidence=ab.get("probability"))
    elif ab.get("predicted_class") == 2 and p_det >= 0.25:
        add("moderate", "ANTIBIOTIC RESPONSE", "Treatment response uncertain",
            "Available data are insufficient or contradictory for a clear response assessment.",
            confidence=ab.get("probability"))

    rec = preds.get("recovery", {})
    if rec.get("predicted_class") == 0 and rec.get("probability", 0) > 0.6:
        add("info", "RECOVERY", "Multiple monitored variables demonstrate an improving trajectory",
            "Recovery model indicates improvement across the monitored window.",
            confidence=rec.get("probability"))

    return alerts


def risk_level_alert(pid: str, hour: int, risk: dict, prev_level: str | None,
                     prev_score: int | None) -> dict | None:
    """Alert when the composite risk score ESCALATES into the HIGH or CRITICAL
    band. Fires on the crossing only, not on every hour spent in the band."""
    order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
    level = risk.get("level")
    if level not in ("HIGH", "CRITICAL") or prev_level not in order:
        return None
    if order[level] <= order[prev_level]:
        return None
    top = next((c for c in risk.get("components", []) if c.get("points")), None)
    driver = f" Largest contributor: {top['label'].lower()} ({top['value']})." if top else ""
    return {"patient_id": pid, "hour": int(hour),
            "severity": "critical" if level == "CRITICAL" else "high",
            "category": "RISK SCORE",
            "title": f"Composite risk level increased to {level}",
            "message": (f"MedVault Composite Risk Score rose from {prev_score} to "
                        f"{risk['score']}/100 ({prev_level} → {level}).{driver} "
                        f"Research indicator, not a validated clinical score. {REVIEW}"),
            "variable": "risk_score", "confidence": None}
