"""Data-quality scoring, what-changed deltas, and exploratory trajectory
similarity for MedVault."""
import numpy as np
import pandas as pd
from functools import lru_cache

from ..config import DATA_DIR

VITALS = ["heart_rate", "sbp", "dbp", "map", "resp_rate", "spo2", "temperature"]
LABS = ["lactate", "wbc", "creatinine", "bilirubin", "platelets"]
FLUIDS = ["urine_output", "fluid_input", "fluid_output"]

WHAT_CHANGED_VARS = {
    "lactate": ("Lactate", "down_good"),
    "heart_rate": ("Heart rate", "down_good"),
    "map": ("MAP", "up_good"),
    "temperature": ("Temperature", "down_good"),
    "resp_rate": ("Respiratory rate", "down_good"),
    "spo2": ("SpO2", "up_good"),
    "urine_output": ("Urine output", "up_good"),
    "creatinine": ("Creatinine", "down_good"),
    "wbc": ("WBC", "down_good"),
}


STALE_LAB_HOURS = 12
LABELS = {"heart_rate": "Heart rate", "sbp": "Systolic BP", "dbp": "Diastolic BP", "map": "MAP",
          "resp_rate": "Respiratory rate", "spo2": "SpO2", "temperature": "Temperature",
          "lactate": "Lactate", "wbc": "WBC", "creatinine": "Creatinine",
          "bilirubin": "Bilirubin", "platelets": "Platelets", "urine_output": "Urine output",
          "fluid_input": "Fluid input", "fluid_output": "Fluid output"}

# Bands for the EXISTING overall score. Laboratory completeness is structurally
# low (labs are sampled every 4-8 h, not hourly), so a fully-monitored patient
# scores in the mid-70s; the bands are set against that ceiling.
QUALITY_BANDS = [(72, "GOOD"), (60, "FAIR"), (0, "POOR")]


def quality_level(overall: float) -> str:
    return next(name for floor, name in QUALITY_BANDS if overall >= floor)


def data_quality(vit_df: pd.DataFrame, has_abx: bool) -> dict:
    n = len(vit_df)
    recent = vit_df.tail(6)

    def completeness(cols):
        return round(float(vit_df[cols].notna().mean().mean()) * 100, 1)

    sections = {
        "vitals": completeness(VITALS),
        "laboratory": completeness(LABS),
        "fluid_records": completeness(FLUIDS),
    }
    # staleness: hours since last non-null lab
    stale = {}
    for c in LABS:
        idx = vit_df[c].last_valid_index()
        stale[c] = int(n - 1 - vit_df.index.get_loc(idx)) if idx is not None else n
    max_stale = max(stale.values()) if stale else 0

    recent_vitals = round(float(recent[VITALS].notna().mean().mean()) * 100, 1)
    score = (0.4 * sections["vitals"] + 0.3 * sections["laboratory"]
             + 0.2 * sections["fluid_records"] + 0.1 * recent_vitals) / 100
    if max_stale > 12:
        score *= 0.85
    if n < 6:
        score *= 0.5

    # --- monitoring detail (additive: the scoring above is unchanged) ---------
    hours = vit_df["hour"].tolist() if "hour" in vit_df else list(range(n))
    current_hour = int(hours[-1]) if hours else None
    last_measured = {}
    for c in LABS:
        idx = vit_df[c].last_valid_index()
        last_measured[c] = int(vit_df.loc[idx, "hour"]) if idx is not None and "hour" in vit_df else None
    latest = vit_df.iloc[-1] if n else None
    missing_latest = ([c for c in VITALS + FLUIDS if pd.isna(latest[c])] if latest is not None else [])
    missing_counts = {c: int(vit_df[c].isna().sum()) for c in VITALS + FLUIDS}
    missing_counts = {c: v for c, v in missing_counts.items() if v > 0}
    lab_timeliness = round(100 * sum(1 for v in stale.values() if v <= STALE_LAB_HOURS) / len(LABS), 1)

    warnings = []
    if n < 6:
        warnings.append({"severity": "warning", "code": "insufficient_history", "variable": None,
                         "title": "Fewer than 6 hours of observations",
                         "message": f"Only {n}h of data are available; model outputs are unreliable "
                                    "until at least 6h exist."})
    for c in LABS:
        if last_measured[c] is None:
            warnings.append({"severity": "warning", "code": "never_measured", "variable": c,
                             "title": f"{LABELS[c]} has never been measured",
                             "message": f"No {LABELS[c].lower()} result exists for this patient."})
        elif stale[c] > STALE_LAB_HOURS:
            warnings.append({"severity": "warning", "code": "stale_lab", "variable": c,
                             "title": f"{LABELS[c]} has not been measured recently",
                             "message": f"Last measurement: {stale[c]} hours ago (hour {last_measured[c]}).",
                             "hours_ago": stale[c], "last_hour": last_measured[c]})
    if missing_latest:
        warnings.append({"severity": "warning", "code": "missing_latest", "variable": None,
                         "title": f"{len(missing_latest)} data field{'s are' if len(missing_latest) != 1 else ' is'} "
                                  "missing in the latest observation",
                         "message": "Missing: " + ", ".join(LABELS[c] for c in missing_latest) + "."})
    if recent_vitals < 90:
        warnings.append({"severity": "warning", "code": "recent_vitals_gap", "variable": None,
                         "title": "Recent vital-sign coverage is incomplete",
                         "message": f"Only {recent_vitals}% of vital-sign values were recorded in the last 6 hours."})
    if not has_abx:
        warnings.append({"severity": "info", "code": "no_antibiotic_record", "variable": None,
                         "title": "No antibiotic record",
                         "message": "No antibiotic exposure is recorded, so the antibiotic-response "
                                    "model has no treatment start to assess against."})

    overall = round(score * 100)
    return {
        "sections": {**sections, "antibiotic_data": 100.0 if has_abx else 0.0,
                     "recent_vitals_6h": recent_vitals},
        "stale_labs_hours": stale,
        "hours_of_data": n,
        "overall_score": overall,
        "sufficient": n >= 6,
        "confidence_modifier": round(score, 3),
        "note": ("Prediction confidence is reduced when completeness is low, labs are stale "
                 "(>12h), or under 6h of observations exist."),
        "level": quality_level(overall),
        "current_hour": current_hour,
        "last_measured_hour": last_measured,
        "lab_timeliness": lab_timeliness,
        "stale_threshold_hours": STALE_LAB_HOURS,
        "missing_latest": missing_latest,
        "missing_counts": missing_counts,
        "warnings": warnings,
        "weights": {"vitals": 0.4, "laboratory": 0.3, "fluid_records": 0.2, "recent_vitals_6h": 0.1},
    }


def what_changed(vit_df: pd.DataFrame, window: int = 6) -> dict:
    """Percent change of key variables: mean of last `window` hours vs the
    preceding `window` hours."""
    if len(vit_df) < window * 2:
        return {"available": False, "reason": f"Needs at least {window * 2}h of data."}
    ff = vit_df[list(WHAT_CHANGED_VARS)].ffill()
    cur = ff.tail(window).mean()
    prev = ff.iloc[-2 * window:-window].mean()
    changes, score = [], 0.0
    for var, (label, direction) in WHAT_CHANGED_VARS.items():
        c, p = cur[var], prev[var]
        if pd.isna(c) or pd.isna(p) or p == 0:
            continue
        pct = (c - p) / abs(p) * 100
        favourable = pct < 0 if direction == "down_good" else pct > 0
        if abs(pct) >= 2:
            score += (1 if favourable else -1) * min(abs(pct), 30) / 30
        changes.append({"variable": var, "label": label,
                        "direction": "up" if pct > 0 else "down",
                        "pct_change": round(pct, 1),
                        "favourable": bool(favourable) if abs(pct) >= 2 else None,
                        "current": round(float(c), 2), "previous": round(float(p), 2)})
    changes.sort(key=lambda x: -abs(x["pct_change"]))
    overall = ("IMPROVING" if score > 1 else "WORSENING" if score < -1 else "MIXED / STABLE")
    return {"available": True, "window_hours": window, "changes": changes,
            "overall_trajectory": overall, "trend_score": round(float(score), 3)}


def trend_series(vit_df: pd.DataFrame, window: int = 6) -> np.ndarray:
    """The favourability score of what_changed() evaluated at EVERY hour.

    Same variables, same 2% dead-band and 30% cap; positive = favourable.
    Hours with less than 2*window of history are NaN. Causal: the value at
    hour h uses rows <= h only."""
    ff = vit_df[list(WHAT_CHANGED_VARS)].ffill()
    cur = ff.rolling(window, min_periods=1).mean()
    prev = cur.shift(window)
    score = np.zeros(len(ff))
    for var, (_, direction) in WHAT_CHANGED_VARS.items():
        c, p = cur[var].to_numpy(dtype=float), prev[var].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            pct = (c - p) / np.abs(p) * 100
        valid = ~np.isnan(c) & ~np.isnan(p) & (p != 0) & (np.abs(pct) >= 2)
        favourable = pct < 0 if direction == "down_good" else pct > 0
        score += np.where(valid, np.where(favourable, 1.0, -1.0)
                          * np.minimum(np.abs(pct), 30) / 30, 0.0)
    score[:2 * window - 1] = np.nan
    return score


@lru_cache(maxsize=1)
def _trajectory_bank():
    """Signature per patient: recent-trend fingerprint + outcome archetype."""
    vitals = pd.read_csv(DATA_DIR / "timeseries.csv")
    patients = pd.read_csv(DATA_DIR / "patients.csv").set_index("patient_id")
    sigs = {}
    for pid, g in vitals.groupby("patient_id"):
        sigs[pid] = _signature(g)
    return sigs, patients["archetype"].to_dict()


def _signature(g: pd.DataFrame) -> np.ndarray:
    g = g.sort_values("hour").tail(24)
    ff = g[["heart_rate", "map", "resp_rate", "temperature", "lactate", "urine_output"]].ffill()
    feats = []
    for c in ff.columns:
        v = ff[c].dropna()
        if len(v) >= 2:
            t = np.arange(len(v))
            feats += [float(v.mean()), float(np.polyfit(t, v.values, 1)[0])]
        else:
            feats += [0.0, 0.0]
    return np.array(feats)


ARCHETYPE_DESC = {
    "stable": "historically stable trajectories",
    "at_risk": "historically at-risk but non-septic trajectories",
    "sepsis_responder": "historical improving-after-treatment trajectories",
    "sepsis_slow": "historical slow-recovery trajectories",
    "sepsis_nonresponder": "historical poor-antibiotic-response trajectories",
    "deteriorating": "historical progressive-deterioration trajectories",
    "fluid_overload": "historical fluid-accumulation trajectories",
}


def similar_trajectories(pid: str, vit_df: pd.DataFrame, k: int = 5) -> dict:
    sigs, archetypes = _trajectory_bank()
    query = _signature(vit_df)
    keys = [p for p in sigs if p != pid]
    mat = np.array([sigs[p] for p in keys])
    mu, sd = mat.mean(axis=0), mat.std(axis=0) + 1e-9
    dists = np.linalg.norm((mat - mu) / sd - (query - mu) / sd, axis=1)
    order = np.argsort(dists)[:k]
    neighbours = [{"patient_id": keys[i], "distance": round(float(dists[i]), 3),
                   "archetype": archetypes[keys[i]]} for i in order]
    top_arch = pd.Series([n["archetype"] for n in neighbours]).mode().iloc[0]
    return {"neighbours": neighbours,
            "summary": f"This patient's recent trajectory resembles {ARCHETYPE_DESC.get(top_arch, top_arch)}.",
            "method": ("Exploratory z-scored nearest-neighbour search over 24h mean+slope "
                       "fingerprints of HR, MAP, RR, temperature, lactate, urine output. "
                       "Similarity is descriptive, not causal."),
            "exploratory": True}
