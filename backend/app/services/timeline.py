"""Clinical timeline: one chronological list of the MEANINGFUL events of a stay.

Nothing here is stored as a "timeline" — events are aggregated on request from
the tables the rest of the platform already writes:

  admission / antibiotic / culture   patients, antibiotic_records
  vital / lab / fluid                vitals (threshold onsets + step changes,
                                     never every raw measurement)
  state_change                       predictions -> rule-based state engine
  prediction                         predictions (sepsis-state classifier)
  risk_change                        risk_scores (band crossings)
  alert                              alerts (consecutive repeats collapsed)
  simulation                         simulation_events (runs collapsed)

Flicker control: a model-derived change is only recorded once the new value
has held for PERSIST_HOURS, or when it is the newest hour on record.
"""
import pandas as pd
from sqlalchemy.orm import Session

from ..database import Patient, AntibioticRecord, Alert, RiskScore, SimulationEvent
from .patient_data import predictions_by_hour, vitals_frame
from .risk import LEVEL_ORDER
from .state_engine import compute_state

PERSIST_HOURS = 3

EVENT_TYPES = {
    "admission": "Admission", "antibiotic": "Antibiotic", "culture": "Microbiology",
    "vital": "Vital signs", "lab": "Laboratory", "fluid": "Fluids",
    "state_change": "Patient state", "prediction": "AI prediction",
    "risk_change": "Risk level", "alert": "Alert", "simulation": "Simulation",
}
# order of events that share an hour: cause before consequence
TYPE_RANK = {t: i for i, t in enumerate(
    ["admission", "simulation", "antibiotic", "culture", "vital", "lab", "fluid",
     "prediction", "state_change", "risk_change", "alert"])}

# (column, label, unit, onset test, resolve test, onset title, resolved title, severity)
VITAL_RULES = [
    ("map", "MAP", "mmHg", lambda v: v < 65, lambda v: v >= 68,
     "MAP fell below 65 mmHg", "MAP recovered above 65 mmHg", "high"),
    ("spo2", "SpO2", "%", lambda v: v < 92, lambda v: v >= 94,
     "SpO2 fell below 92%", "SpO2 recovered above 92%", "high"),
    ("heart_rate", "Heart rate", "bpm", lambda v: v > 110, lambda v: v <= 100,
     "Heart rate rose above 110 bpm", "Heart rate settled below 110 bpm", "moderate"),
    ("resp_rate", "Respiratory rate", "/min", lambda v: v > 24, lambda v: v <= 21,
     "Respiratory rate rose above 24 /min", "Respiratory rate settled below 24 /min", "moderate"),
    ("temperature", "Temperature", "°C", lambda v: v >= 38.3, lambda v: v < 37.8,
     "Fever: temperature reached 38.3 °C", "Temperature settled below 38.3 °C", "moderate"),
]

# (column, label, unit, min absolute change, min relative change, worse when rising, decimals)
LAB_RULES = [
    ("lactate", "Lactate", "mmol/L", 0.6, 0.25, True, 1),
    ("creatinine", "Creatinine", "mg/dL", 0.3, 0.25, True, 2),
    ("wbc", "WBC", "×10⁹/L", 3.0, 0.25, True, 1),
    ("bilirubin", "Bilirubin", "mg/dL", 0.5, 0.30, True, 1),
    ("platelets", "Platelets", "×10⁹/L", 40.0, 0.25, False, 0),
]
FLUID_MILESTONES = [2500, 4000]      # mL cumulative balance (the FS label thresholds)
OLIGURIA_ML_H = 30


def _ev(hour, type_, title, detail, severity=None, value=None, source="observed", **extra):
    return {"hour": int(hour), "type": type_, "title": title, "detail": detail,
            "severity": severity, "value": value, "source": source, **extra}


def _persistent_changes(hours: list[int], labels: list):
    """Yield (hour, previous, new) for label changes that hold PERSIST_HOURS
    (or reach the end of the record)."""
    current = None
    n = len(labels)
    for i, lab in enumerate(labels):
        if lab == current or lab is None:
            continue
        run = 1
        while i + run < n and labels[i + run] == lab and run < PERSIST_HOURS:
            run += 1
        if run >= PERSIST_HOURS or i + run == n:
            yield hours[i], current, lab
            current = lab


def _vital_events(vit: pd.DataFrame) -> list[dict]:
    out = []
    hours = vit["hour"].tolist()
    for col, label, unit, onset, resolve, t_on, t_off, sev in VITAL_RULES:
        smooth = vit[col].rolling(3, min_periods=2).mean().tolist()
        active = False
        for h, v in zip(hours, smooth):
            if v is None or pd.isna(v):
                continue
            if not active and onset(v):
                active = True
                out.append(_ev(h, "vital", t_on, f"3-hour mean {label} {v:.1f} {unit}.",
                               severity=sev, value=f"{v:.1f} {unit}"))
            elif active and resolve(v):
                active = False
                out.append(_ev(h, "vital", t_off, f"3-hour mean {label} {v:.1f} {unit}.",
                               severity="good", value=f"{v:.1f} {unit}"))
    return out


def _lab_events(vit: pd.DataFrame) -> list[dict]:
    """Step changes against the last REPORTED value, so a slow drift produces
    a few stepwise events instead of one per measurement."""
    out = []
    for col, label, unit, min_abs, min_rel, up_bad, dp in LAB_RULES:
        base = None
        for h, v in zip(vit["hour"], vit[col]):
            if pd.isna(v):
                continue
            if base is None:
                base = v
                continue
            diff = v - base
            if abs(diff) >= min_abs and abs(diff) >= min_rel * abs(base):
                rising = diff > 0
                worse = rising == up_bad
                out.append(_ev(
                    h, "lab", f"{label} {'increasing' if rising else 'decreasing'}",
                    f"{label} {'increased' if rising else 'decreased'} from "
                    f"{base:.{dp}f} to {v:.{dp}f} {unit}.",
                    severity="high" if worse else "good", value=f"{v:.{dp}f} {unit}"))
                base = v
    return out


def _fluid_events(vit: pd.DataFrame) -> list[dict]:
    out = []
    hours = vit["hour"].tolist()
    cum = (vit["fluid_input"].fillna(0) - vit["fluid_output"].fillna(0)).cumsum().tolist()
    for m in FLUID_MILESTONES:
        hit = next((i for i, c in enumerate(cum) if c > m), None)
        if hit is not None:
            out.append(_ev(hours[hit], "fluid", f"Cumulative fluid balance passed +{m:,} mL",
                           f"Cumulative balance {cum[hit]:,.0f} mL since monitoring started.",
                           severity="high" if m >= 4000 else "moderate",
                           value=f"{cum[hit]:,.0f} mL"))
    uo = vit["urine_output"].rolling(6, min_periods=4).mean().tolist()
    active = False
    for h, v in zip(hours, uo):
        if v is None or pd.isna(v):
            continue
        if not active and v < OLIGURIA_ML_H:
            active = True
            out.append(_ev(h, "fluid", f"Urine output fell below {OLIGURIA_ML_H} mL/h",
                           f"6-hour mean urine output {v:.0f} mL/h.", severity="high",
                           value=f"{v:.0f} mL/h"))
        elif active and v >= OLIGURIA_ML_H + 10:
            active = False
            out.append(_ev(h, "fluid", f"Urine output recovered above {OLIGURIA_ML_H} mL/h",
                           f"6-hour mean urine output {v:.0f} mL/h.", severity="good",
                           value=f"{v:.0f} mL/h"))
    return out


def _collapse_alerts(alerts: list[Alert]) -> list[dict]:
    """Merge the same alert title firing on consecutive hours into one event."""
    out = []
    open_: dict[str, dict] = {}
    for a in sorted(alerts, key=lambda a: (a.hour, a.id)):
        ev = open_.get(a.title)
        if ev and a.hour - ev["_last"] <= 1:
            ev["_last"] = a.hour
            if a.severity != ev["severity"] and ev["_rank"] > _SEV_RANK.get(a.severity, 9):
                ev["severity"], ev["_rank"] = a.severity, _SEV_RANK.get(a.severity, 9)
            continue
        ev = _ev(a.hour, "alert", a.title, a.message, severity=a.severity,
                 value=f"{a.confidence:.0%}" if a.confidence is not None else None,
                 source="rule", category=a.category, alert_id=a.id,
                 acknowledged=bool(a.acknowledged))
        ev["_last"], ev["_rank"] = a.hour, _SEV_RANK.get(a.severity, 9)
        open_[a.title] = ev
        out.append(ev)
    for ev in out:
        last = ev.pop("_last")
        ev.pop("_rank")
        if last > ev["hour"]:
            ev["until_hour"] = last
            ev["detail"] += f" Active from hour {ev['hour']} to hour {last}."
    return out


_SEV_RANK = {"critical": 0, "high": 1, "moderate": 2, "info": 3}
_RISK_SEV = {"LOW": "good", "MODERATE": "moderate", "HIGH": "high", "CRITICAL": "critical"}
_TONE_SEV = {"green": "good", "blue": "good", "yellow": "moderate", "orange": "high",
             "red": "critical", "gray": "info"}


def build_timeline(db: Session, patient: Patient) -> list[dict]:
    pid = patient.patient_id
    events = [_ev(0, "admission", "ICU admission",
                  "ICU monitoring initiated.", severity="info")]

    for a in db.query(AntibioticRecord).filter(AntibioticRecord.patient_id == pid).all():
        events.append(_ev(
            a.start_hour, "antibiotic", f"Antibiotic treatment recorded ({a.abx_class})",
            f"{a.abx_class} started, planned duration {a.duration_hours}h. "
            + ("Blood culture taken." if a.culture_taken else "No culture recorded."),
            severity="info", value=a.abx_class))
        if a.culture_taken:
            result_hour = max(a.start_hour - 2, 0) + 24
            if result_hour <= patient.n_hours - 1:
                if a.culture_positive:
                    title = f"Culture result: {a.organism or 'organism identified'}"
                    detail = ("Positive blood culture, "
                              + ("susceptible to the recorded antibiotic class."
                                 if a.susceptible else "reduced susceptibility reported."))
                    sev = "info" if a.susceptible else "high"
                else:
                    title, detail, sev = "Culture result: no growth", "Blood culture negative.", "info"
                events.append(_ev(result_hour, "culture", title, detail, severity=sev))

    vit = vitals_frame(db, pid)
    if len(vit):
        events += _vital_events(vit) + _lab_events(vit) + _fluid_events(vit)

    by_hour = predictions_by_hour(db, pid)
    hours = list(by_hour)
    if hours:
        engine = [compute_state(by_hour[h], h + 1) for h in hours]
        labels = [e["label"] if e["state"] is not None else None for e in engine]
        by_label = {e["label"]: e for e in engine}
        for h, prev, new in _persistent_changes(hours, labels):
            e = next(x for x, hh in zip(engine, hours) if hh == h)
            events.append(_ev(
                h, "state_change",
                f"Patient state: {new}" if prev is None else f"State changed: {prev} → {new}",
                "; ".join(e["reasons"]) + ". Rule-based state engine.",
                severity=_TONE_SEV.get(by_label[new]["tone"]), value=new, source="rule"))

        ss = [by_hour[h].get("sepsis_state", {}).get("predicted_label") for h in hours]
        for h, prev, new in _persistent_changes(hours, ss):
            if prev is None:
                continue
            p = by_hour[h]["sepsis_state"]["probability"]
            events.append(_ev(h, "prediction", f"Sepsis-state model: {new}",
                              f"Classifier output changed from {prev} to {new} "
                              f"(model probability {p:.0%}).",
                              severity=None, value=f"{p:.0%}", source="model"))

    risk = (db.query(RiskScore.hour, RiskScore.score, RiskScore.level)
            .filter(RiskScore.patient_id == pid).order_by(RiskScore.hour).all())
    scored = [(h, s, lv) for h, s, lv in risk if s is not None]
    score_at = {h: s for h, s, _ in scored}
    for h, prev, new in _persistent_changes([r[0] for r in scored], [r[2] for r in scored]):
        if prev is None:
            events.append(_ev(h, "risk_change", f"Initial risk level: {new}",
                              f"Composite risk score {score_at[h]}/100.",
                              severity=_RISK_SEV[new], value=f"{score_at[h]}/100", source="model"))
            continue
        up = LEVEL_ORDER[new] > LEVEL_ORDER[prev]
        events.append(_ev(
            h, "risk_change", f"Risk level {'increased' if up else 'decreased'} to {new}",
            f"Composite risk score {score_at[h]}/100 ({prev} → {new}).",
            severity=_RISK_SEV[new] if up else "good", value=f"{score_at[h]}/100",
            source="model"))

    events += _collapse_alerts(db.query(Alert).filter(Alert.patient_id == pid).all())

    sims = (db.query(SimulationEvent).filter(SimulationEvent.patient_id == pid)
            .order_by(SimulationEvent.hour).all())
    run = None
    for s in sims:
        if run and s.scenario == run["scenario"] and s.hour == run["until_hour"] + 1:
            run["until_hour"] = s.hour
            continue
        run = _ev(s.hour, "simulation", f"Simulation: {s.scenario} scenario",
                  "", severity="info", source="simulation",
                  scenario=s.scenario, until_hour=s.hour, simulated=True)
        events.append(run)
    for e in events:
        if e["type"] == "simulation":
            n = e["until_hour"] - e["hour"] + 1
            e["detail"] = (f"{n} synthetic hour{'s' if n != 1 else ''} generated "
                           f"(hour {e['hour']}" + (f"–{e['until_hour']}" if n > 1 else "")
                           + f") under the '{e['scenario']}' scenario and run through the full pipeline.")

    first_sim = sims[0].hour if sims else None
    for e in events:
        e.setdefault("simulated", first_sim is not None and e["hour"] >= first_sim)
        e["type_label"] = EVENT_TYPES[e["type"]]
    events.sort(key=lambda e: (e["hour"], TYPE_RANK[e["type"]]))
    return events
