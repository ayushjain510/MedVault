"""Synthetic ICU patient data simulator for MedVault.

Generates clearly-labeled SYNTHETIC demonstration data. No real patient data.
Each patient follows a trajectory archetype that drives physiologically-plausible
hourly time series of vitals, labs, fluids and antibiotic records.
"""
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from pathlib import Path

RNG_SEED = 42

ARCHETYPES = [
    "stable",              # never septic
    "at_risk",             # abnormal trends, no full sepsis
    "sepsis_responder",    # sepsis -> antibiotics -> recovery
    "sepsis_slow",         # sepsis -> slow/partial response
    "sepsis_nonresponder", # sepsis -> poor antibiotic response, persistent
    "deteriorating",       # progressive deterioration, escalation
    "fluid_overload",      # sepsis + positive fluid balance concern
]

ARCHETYPE_WEIGHTS = [0.28, 0.15, 0.20, 0.10, 0.09, 0.10, 0.08]

# Sepsis states (multi-class labels)
STATE_STABLE = 0
STATE_AT_RISK = 1
STATE_ACTIVE_SEPSIS = 2
STATE_SEVERE = 3
STATE_TREATMENT_RESPONSE = 4
STATE_RECOVERY = 5
STATE_NON_RESPONDING = 6
STATE_ESCALATION = 7

STATE_NAMES = {
    0: "Stable / Low Concern",
    1: "At Risk",
    2: "Active Sepsis / Concerning",
    3: "Severe / Deteriorating",
    4: "Treatment Response",
    5: "Recovery",
    6: "Persistent / Non-responding",
    7: "Escalation Required",
}

ABX_CLASSES = ["Beta-lactam", "Carbapenem", "Fluoroquinolone", "Glycopeptide", "Aminoglycoside"]


@dataclass
class Baselines:
    hr: float
    sbp: float
    dbp: float
    rr: float
    spo2: float
    temp: float
    lactate: float
    wbc: float
    creatinine: float
    bilirubin: float
    platelets: float
    urine: float  # mL/hr


def _baselines(rng) -> Baselines:
    return Baselines(
        hr=rng.normal(78, 8),
        sbp=rng.normal(122, 10),
        dbp=rng.normal(74, 7),
        rr=rng.normal(15, 2),
        spo2=rng.normal(97.5, 1.0),
        temp=rng.normal(36.9, 0.25),
        lactate=rng.normal(1.1, 0.25),
        wbc=rng.normal(7.5, 1.5),
        creatinine=rng.normal(0.9, 0.15),
        bilirubin=rng.normal(0.7, 0.2),
        platelets=rng.normal(260, 40),
        urine=rng.normal(70, 12),
    )


def _severity_curve(archetype: str, n_hours: int, rng) -> tuple[np.ndarray, dict]:
    """Return severity in [0,1] per hour plus event metadata."""
    t = np.arange(n_hours, dtype=float)
    meta = {"abx_start": None, "abx_class": None, "onset": None}
    sev = np.zeros(n_hours)

    if archetype == "stable":
        sev = np.clip(rng.normal(0.05, 0.03, n_hours), 0, 0.18)
    elif archetype == "at_risk":
        peak = rng.uniform(0.25, 0.42)
        onset = int(rng.uniform(6, n_hours * 0.4))
        ramp = np.clip((t - onset) / rng.uniform(10, 20), 0, 1)
        sev = ramp * peak + rng.normal(0, 0.03, n_hours)
        meta["onset"] = onset
    else:
        onset = int(rng.uniform(4, min(18, n_hours * 0.3)))
        meta["onset"] = onset
        ramp_len = rng.uniform(6, 14)
        rise = np.clip((t - onset) / ramp_len, 0, 1)
        peak = rng.uniform(0.6, 0.85)
        sev = rise * peak
        abx_start = onset + int(rng.uniform(2, 8))
        meta["abx_start"] = abx_start
        meta["abx_class"] = ABX_CLASSES[rng.integers(len(ABX_CLASSES))]
        post = t - abx_start
        if archetype == "sepsis_responder":
            lag = rng.uniform(4, 8)
            rec = np.clip((post - lag) / rng.uniform(14, 24), 0, 1)
            sev = sev * (1 - 0.9 * rec)
        elif archetype == "sepsis_slow":
            lag = rng.uniform(8, 14)
            rec = np.clip((post - lag) / rng.uniform(30, 48), 0, 1)
            sev = sev * (1 - 0.55 * rec)
        elif archetype == "sepsis_nonresponder":
            drift = np.clip(post / 60, 0, 1) * rng.uniform(0.0, 0.12)
            sev = np.minimum(sev + drift, 0.95)
        elif archetype == "deteriorating":
            drift = np.clip(post / rng.uniform(20, 30), 0, 1) * rng.uniform(0.15, 0.3)
            sev = np.minimum(sev + drift, 1.0)
        elif archetype == "fluid_overload":
            lag = rng.uniform(6, 10)
            rec = np.clip((post - lag) / rng.uniform(24, 40), 0, 1)
            sev = sev * (1 - 0.5 * rec)
        sev = sev + rng.normal(0, 0.025, n_hours)

    return np.clip(sev, 0, 1), meta


def _label_states(sev: np.ndarray, meta: dict, archetype: str) -> np.ndarray:
    """Derive ground-truth state labels from severity + trend + treatment context."""
    n = len(sev)
    states = np.zeros(n, dtype=int)
    smooth = pd.Series(sev).rolling(5, min_periods=1, center=True).mean().values
    trend = np.gradient(smooth)
    abx = meta["abx_start"]
    for i in range(n):
        s, tr = smooth[i], trend[i]
        post_abx = abx is not None and i >= abx + 6
        if s < 0.18:
            if post_abx and archetype in ("sepsis_responder", "sepsis_slow", "fluid_overload"):
                states[i] = STATE_RECOVERY
            else:
                states[i] = STATE_STABLE
        elif s < 0.35:
            if post_abx and tr < -0.004:
                states[i] = STATE_TREATMENT_RESPONSE
            elif post_abx and archetype in ("sepsis_responder", "sepsis_slow"):
                states[i] = STATE_TREATMENT_RESPONSE if tr < 0.001 else STATE_AT_RISK
            else:
                states[i] = STATE_AT_RISK
        elif s < 0.6:
            if post_abx and tr < -0.004:
                states[i] = STATE_TREATMENT_RESPONSE
            elif post_abx and abs(tr) <= 0.004 and i >= abx + 16:
                states[i] = STATE_NON_RESPONDING
            else:
                states[i] = STATE_ACTIVE_SEPSIS
        else:
            if tr > 0.006 and s > 0.75:
                states[i] = STATE_ESCALATION
            elif post_abx and i >= abx + 16 and tr >= -0.002:
                states[i] = STATE_NON_RESPONDING
            else:
                states[i] = STATE_SEVERE
    return states


def _vitals_from_severity(b: Baselines, sev: np.ndarray, rng, fluid_overload: bool) -> pd.DataFrame:
    n = len(sev)
    noise = lambda s: rng.normal(0, s, n)
    ar = np.zeros(n)  # AR(1) correlated noise
    for i in range(1, n):
        ar[i] = 0.8 * ar[i - 1] + rng.normal(0, 0.35)

    hr = b.hr + sev * 45 + ar * 3 + noise(2.5)
    sbp = b.sbp - sev * 38 + ar * -2 + noise(4)
    dbp = b.dbp - sev * 22 + noise(3)
    mapv = dbp + (sbp - dbp) / 3
    rr = b.rr + sev * 13 + noise(1.2)
    spo2 = np.clip(b.spo2 - sev * 7 + noise(0.6), 78, 100)
    temp = b.temp + sev * 2.4 + noise(0.15)
    lactate = np.clip(b.lactate + sev**1.3 * 5.5 + noise(0.2), 0.4, 15)
    wbc = np.clip(b.wbc + sev * 12 + noise(0.8), 1, 40)
    creat = np.clip(b.creatinine + np.cumsum(sev) * 0.012 * (0.5 + sev) / n * 24 + noise(0.05), 0.4, 8)
    bili = np.clip(b.bilirubin + sev * 2.2 + noise(0.1), 0.2, 12)
    plt = np.clip(b.platelets - np.cumsum(sev) / n * 24 * 6 - sev * 60 + noise(8), 15, 500)
    urine = np.clip(b.urine * (1 - sev * 0.75) + noise(5), 0, 200)
    if fluid_overload:
        urine = urine * 0.6

    # fluids: input rises with severity (resuscitation), maintenance ~80 mL/h
    fluid_in = 80 + sev * 260 + np.abs(noise(15))
    if fluid_overload:
        fluid_in = fluid_in * 1.5
    fluid_out = urine + 20 + np.abs(noise(8))

    return pd.DataFrame({
        "heart_rate": hr.round(1), "sbp": sbp.round(1), "dbp": dbp.round(1),
        "map": mapv.round(1), "resp_rate": rr.round(1), "spo2": spo2.round(1),
        "temperature": temp.round(2), "lactate": lactate.round(2), "wbc": wbc.round(2),
        "creatinine": creat.round(2), "bilirubin": bili.round(2), "platelets": plt.round(0),
        "urine_output": urine.round(1), "fluid_input": fluid_in.round(1),
        "fluid_output": fluid_out.round(1),
    })


def _inject_missingness(df: pd.DataFrame, rng) -> pd.DataFrame:
    """Labs are measured every 4-8h in reality; vitals mostly continuous."""
    df = df.copy()
    lab_cols = ["lactate", "wbc", "creatinine", "bilirubin", "platelets"]
    n = len(df)
    for c in lab_cols:
        interval = int(rng.integers(4, 9))
        offset = int(rng.integers(0, interval))
        mask = np.ones(n, dtype=bool)
        mask[offset::interval] = False  # False = keep
        df.loc[mask, c] = np.nan
    for c in ["heart_rate", "sbp", "dbp", "map", "resp_rate", "spo2", "temperature"]:
        drop = rng.random(n) < 0.03
        df.loc[drop, c] = np.nan
    return df


def generate_dataset(n_patients: int = 240, seed: int = RNG_SEED, out_dir: str | Path = None):
    rng = np.random.default_rng(seed)
    vitals_rows, patients_rows, abx_rows = [], [], []

    for pid_i in range(n_patients):
        pid = f"P{pid_i + 1:04d}"
        archetype = rng.choice(ARCHETYPES, p=ARCHETYPE_WEIGHTS)
        n_hours = int(rng.integers(48, 97))
        age = int(np.clip(rng.normal(63, 15), 18, 95))
        sex = rng.choice(["M", "F"])
        b = _baselines(rng)
        if age > 70:
            b.creatinine += 0.15
            b.sbp += 6

        sev, meta = _severity_curve(archetype, n_hours, rng)
        states = _label_states(sev, meta, archetype)
        vit = _vitals_from_severity(b, sev, rng, archetype == "fluid_overload")
        vit = _inject_missingness(vit, rng)
        vit.insert(0, "hour", np.arange(n_hours))
        vit.insert(0, "patient_id", pid)
        vit["severity"] = sev.round(4)          # ground-truth latent (never a model input)
        vit["state"] = states
        vitals_rows.append(vit)

        patients_rows.append({
            "patient_id": pid, "age": age, "sex": sex, "archetype": archetype,
            "n_hours": n_hours, "admission_offset_hours": int(rng.integers(0, 240)),
            "abx_start": meta["abx_start"], "onset": meta["onset"],
        })
        if meta["abx_start"] is not None:
            abx_rows.append({
                "patient_id": pid, "start_hour": meta["abx_start"],
                "abx_class": meta["abx_class"],
                "duration_hours": int(n_hours - meta["abx_start"]),
                "culture_taken": bool(rng.random() < 0.85),
                "culture_positive": bool(rng.random() < 0.6),
                "organism": rng.choice(["E. coli", "S. aureus", "K. pneumoniae", "P. aeruginosa", "S. pneumoniae"]) if rng.random() < 0.6 else None,
                "susceptible": bool(rng.random() < (0.85 if archetype in ("sepsis_responder", "sepsis_slow", "fluid_overload") else 0.35)),
            })

    vitals = pd.concat(vitals_rows, ignore_index=True)
    patients = pd.DataFrame(patients_rows)
    abx = pd.DataFrame(abx_rows)

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        vitals.to_csv(out / "timeseries.csv", index=False)
        patients.to_csv(out / "patients.csv", index=False)
        abx.to_csv(out / "antibiotics.csv", index=False)
        with open(out / "META.json", "w") as f:
            json.dump({"synthetic": True, "seed": seed, "n_patients": n_patients,
                       "note": "SYNTHETIC DEMONSTRATION DATA - not real patients",
                       "state_names": STATE_NAMES}, f, indent=2)
    return patients, vitals, abx


if __name__ == "__main__":
    p, v, a = generate_dataset(out_dir=Path(__file__).parent / "data")
    print(f"patients={len(p)} rows={len(v)} abx={len(a)}")
    print(v["state"].value_counts().sort_index())
    print(p["archetype"].value_counts())
