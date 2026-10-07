"""Temporal feature engineering for MedVault.

All features use ONLY past and current information (rolling windows ending at
the current hour) — no future leakage. The latent `severity` column is never
used as an input. Missing labs are forward-filled per patient (clinically
justified: last known lab stands until re-measured) with missingness
indicators and hours-since-measurement features.
"""
import numpy as np
import pandas as pd

VITAL_COLS = ["heart_rate", "sbp", "dbp", "map", "resp_rate", "spo2", "temperature"]
LAB_COLS = ["lactate", "wbc", "creatinine", "bilirubin", "platelets"]
FLUID_COLS = ["urine_output", "fluid_input", "fluid_output"]
SIGNAL_COLS = VITAL_COLS + LAB_COLS + FLUID_COLS
WINDOWS = [3, 6, 12, 24]

FEATURE_LABELS = {
    "heart_rate": "Heart rate", "sbp": "Systolic BP", "dbp": "Diastolic BP",
    "map": "MAP", "resp_rate": "Respiratory rate", "spo2": "SpO2",
    "temperature": "Temperature", "lactate": "Lactate", "wbc": "WBC",
    "creatinine": "Creatinine", "bilirubin": "Bilirubin", "platelets": "Platelets",
    "urine_output": "Urine output", "fluid_input": "Fluid input",
    "fluid_output": "Fluid output",
}


def humanize_feature(name: str) -> str:
    for k, v in sorted(FEATURE_LABELS.items(), key=lambda x: -len(x[0])):
        if name.startswith(k):
            suffix = name[len(k):].lstrip("_")
            nice = {"mean": "mean", "min": "min", "max": "max", "std": "variability",
                    "slope": "trend", "delta": "change", "missing": "not measured",
                    "hrs_since": "hours since measured", "cur": "current"}
            for s_key, s_val in nice.items():
                if suffix.startswith(s_key):
                    w = suffix[len(s_key):].lstrip("_")
                    return f"{v} {s_val}" + (f" ({w}h)" if w else "")
            return f"{v} {suffix}" if suffix else v
    special = {"age": "Age", "sex_m": "Sex (male)", "hour": "Hours in ICU",
               "on_abx": "On antibiotics", "hrs_since_abx": "Hours since antibiotic start",
               "cum_fluid_balance": "Cumulative fluid balance", "net_fluid_6h": "Net fluid balance (6h)",
               "shock_index": "Shock index (HR/SBP)"}
    return special.get(name, name)


def _slope(x: pd.Series) -> float:
    v = x.dropna()
    if len(v) < 2:
        return 0.0
    t = np.arange(len(v))
    return float(np.polyfit(t, v.values, 1)[0])


def build_features(vitals: pd.DataFrame, patients: pd.DataFrame, abx: pd.DataFrame) -> pd.DataFrame:
    """Return one feature row per (patient, hour)."""
    frames = []
    abx_map = abx.set_index("patient_id")["start_hour"].to_dict() if len(abx) else {}
    pat_map = patients.set_index("patient_id")[["age", "sex"]].to_dict("index")

    for pid, g in vitals.groupby("patient_id", sort=False):
        g = g.sort_values("hour").reset_index(drop=True)
        f = pd.DataFrame({"patient_id": pid, "hour": g["hour"]})

        for c in LAB_COLS:
            measured = g[c].notna()
            f[f"{c}_missing"] = (~measured).astype(int)
            hrs = np.zeros(len(g))
            last = -1
            for i, m in enumerate(measured):
                if m:
                    last = i
                hrs[i] = i - last if last >= 0 else i + 1
            f[f"{c}_hrs_since"] = hrs

        sig = g[SIGNAL_COLS].ffill()

        for c in SIGNAL_COLS:
            f[f"{c}_cur"] = sig[c]
            for w in WINDOWS:
                roll = sig[c].rolling(w, min_periods=1)
                f[f"{c}_mean_{w}"] = roll.mean()
                if w in (6, 24):
                    f[f"{c}_min_{w}"] = roll.min()
                    f[f"{c}_max_{w}"] = roll.max()
                    f[f"{c}_std_{w}"] = roll.std().fillna(0)
            f[f"{c}_slope_6"] = sig[c].rolling(6, min_periods=2).apply(_slope, raw=False).fillna(0)
            f[f"{c}_slope_12"] = sig[c].rolling(12, min_periods=2).apply(_slope, raw=False).fillna(0)
            f[f"{c}_delta_3"] = (sig[c] - sig[c].shift(3)).fillna(0)

        f["shock_index"] = (sig["heart_rate"] / sig["sbp"].clip(lower=40)).round(3)
        net = sig["fluid_input"] - sig["fluid_output"]
        f["cum_fluid_balance"] = net.cumsum()
        f["net_fluid_6h"] = net.rolling(6, min_periods=1).sum()

        info = pat_map[pid]
        f["age"] = info["age"]
        f["sex_m"] = int(info["sex"] == "M")
        ab_start = abx_map.get(pid)
        if ab_start is not None:
            f["on_abx"] = (g["hour"] >= ab_start).astype(int)
            f["hrs_since_abx"] = np.clip(g["hour"] - ab_start, 0, None) * f["on_abx"]
        else:
            f["on_abx"] = 0
            f["hrs_since_abx"] = 0.0

        if "state" in g.columns:
            f["state"] = g["state"].values
        frames.append(f)

    feats = pd.concat(frames, ignore_index=True)
    return feats


def _norm(v, lo, hi):
    """Scale to [0,1] with clipping; NaN-safe."""
    return np.clip((np.asarray(v, dtype=float) - lo) / (hi - lo), 0, 1)


def organ_dysfunction_score(g: pd.DataFrame) -> np.ndarray:
    """SOFA-inspired organ-dysfunction score in [0,1] from OBSERVABLES only.

    Components: cardiovascular (MAP), renal (creatinine, urine output),
    hepatic (bilirubin), coagulation (platelets), respiratory (SpO2).
    Deliberately excludes temperature/WBC/lactate so that this score and the
    infection-marker score below are built from disjoint variables.
    """
    cardio = _norm(-g["map"], -75, -55)              # lower MAP = worse
    renal = 0.5 * _norm(g["creatinine"], 0.9, 3.0) + 0.5 * _norm(-g["urine_output"], -60, -15)
    hepatic = _norm(g["bilirubin"], 0.8, 4.0)
    coag = _norm(-g["platelets"], -220, -90)
    resp = _norm(-g["spo2"], -97, -88)
    score = (0.28 * cardio + 0.28 * renal + 0.16 * hepatic
             + 0.14 * coag + 0.14 * resp)
    return pd.Series(score).rolling(4, min_periods=1, center=True).mean().values


def infection_marker_score(g: pd.DataFrame) -> np.ndarray:
    """Infection-response score in [0,1] from temperature, WBC and lactate only.

    These are the classical markers of response to antimicrobial therapy and are
    disjoint from the organ-dysfunction components above.
    """
    fever = _norm(np.abs(g["temperature"] - 37.0), 0.3, 2.4)
    wbc = _norm(np.abs(g["wbc"] - 7.5), 2.0, 11.0)
    lac = _norm(g["lactate"], 1.2, 5.5)
    score = 0.34 * fever + 0.30 * wbc + 0.36 * lac
    return pd.Series(score).rolling(4, min_periods=1, center=True).mean().values


def build_targets(feats: pd.DataFrame, vitals: pd.DataFrame) -> pd.DataFrame:
    """Attach the prediction targets.

    Each task is derived from a DISTINCT observable subsystem so the labels are
    not four transformations of one latent variable:

      recovery (RT)     organ-dysfunction score (MAP, creatinine, urine output,
                        bilirubin, platelets, SpO2), FORWARD 12 h
      antibiotic (AR)   infection markers (temperature, WBC, lactate),
                        FORWARD 12 h, gated on antibiotic exposure
      fluid (FS)        fluid/renal observables (cumulative balance, urine
                        output, creatinine trend, MAP) — current-state
                        characterization
      deterioration     composite latent severity, FORWARD 6/12/24 h

    RT and AR look forward, so the models must PREDICT a future trajectory
    rather than recompute a concurrent one. All future-looking values are used
    for targets only and never as features.
    """
    out = feats.copy()
    sev_map = vitals.set_index(["patient_id", "hour"])["severity"]
    # forward-fill observables so sparse labs do not create spurious label gaps
    obs_cols = ["map", "creatinine", "urine_output", "bilirubin", "platelets",
                "spo2", "temperature", "wbc", "lactate"]
    vit = vitals.sort_values(["patient_id", "hour"]).copy()
    vit[obs_cols] = vit.groupby("patient_id")[obs_cols].ffill().bfill()
    vit = vit.set_index(["patient_id", "hour"])

    RT_HORIZON = AR_HORIZON = 12

    det6, det12, det24, recovery, abx_resp, fluid_state = [], [], [], [], [], []
    for pid, g in out.groupby("patient_id", sort=False):
        hours = g["hour"].values
        n = len(hours)
        gv = vit.loc[pid].reindex(hours)

        # --- deterioration: composite latent severity, forward-looking -------
        sev = sev_map.loc[pid].reindex(hours).values
        s = pd.Series(sev).rolling(4, min_periods=1, center=True).mean().values
        for k, arr in ((6, det6), (12, det12), (24, det24)):
            fut = np.array([s[min(i + k, n - 1)] for i in range(n)])
            arr.extend(((fut - s > 0.08) | ((fut > 0.6) & (fut > s))).astype(int))

        # --- recovery: organ-dysfunction trajectory over the NEXT 12 h -------
        # Rows within RT_HORIZON of the end of the record are RIGHT-CENSORED:
        # the future window is not observable, so no valid label exists. They
        # are marked -1 and excluded from training (never given a fake label).
        # The model still predicts on them at inference, which is the whole
        # point — a live system forecasts forward from "now".
        organ = organ_dysfunction_score(gv)
        organ_future = np.array([organ[min(i + RT_HORIZON, n - 1)] for i in range(n)])
        d_organ = organ_future - organ
        for i in range(n):
            # Thresholds are set from the observed d_organ distribution
            # (≈p10 / p27 / p80) so no class is too rare to learn; see
            # docs/label_definitions.md.
            if i + RT_HORIZON > n - 1:
                recovery.append(-1)         # right-censored: excluded from training
            elif hours[i] < 6:
                recovery.append(5)          # RT-5 insufficient evidence
            elif d_organ[i] < -0.045:
                recovery.append(0)          # RT-0 improving
            elif d_organ[i] > 0.060:
                recovery.append(4)          # RT-4 worsening
            elif d_organ[i] < -0.008:
                recovery.append(2)          # RT-2 slow recovery
            elif organ[i] > 0.25:
                recovery.append(3)          # RT-3 persistent concern
            else:
                recovery.append(1)          # RT-1 stable

        # --- antibiotic response: infection markers over the NEXT 12 h ------
        infl = infection_marker_score(gv)
        infl_future = np.array([infl[min(i + AR_HORIZON, n - 1)] for i in range(n)])
        d_infl = infl_future - infl
        infl_vol = pd.Series(infl).rolling(12, min_periods=3).std().values
        on = g["on_abx"].values
        hrs = g["hrs_since_abx"].values
        for i in range(n):
            vol = infl_vol[i] if not np.isnan(infl_vol[i]) else 0
            if i + AR_HORIZON > n - 1:
                abx_resp.append(-1)         # right-censored: excluded from training
            elif not on[i] or hrs[i] < 4:
                abx_resp.append(2)          # AR-2 uncertain / insufficient
            elif vol > 0.10 and abs(d_infl[i]) < 0.03:
                abx_resp.append(2)          # contradictory: volatile, no trend
            elif d_infl[i] < -0.05:
                abx_resp.append(0)          # AR-0 improving
            elif d_infl[i] > 0.12:
                abx_resp.append(4)          # AR-4 worsening
            elif infl[i] > 0.35:
                abx_resp.append(3)          # AR-3 poor response
            else:
                abx_resp.append(1)          # AR-1 stable / no clear change

        # --- fluid status: fluid + renal observables only --------------------
        cum = g["cum_fluid_balance"].values
        net6 = g["net_fluid_6h"].values
        uo6 = g["urine_output_mean_6"].values
        mapv = gv["map"].values
        creat_slope = pd.Series(gv["creatinine"].values).diff().rolling(
            12, min_periods=3).mean().values
        for i in range(n):
            cs = creat_slope[i] if not np.isnan(creat_slope[i]) else 0
            if hours[i] < 6:
                fluid_state.append(5)       # FS-5 insufficient data
            elif uo6[i] < 25 and mapv[i] < 66:
                fluid_state.append(4)       # FS-4 inadequate hemodynamic response
            elif cum[i] > 4000 and (uo6[i] < 40 or cs > 0.004):
                fluid_state.append(3)       # FS-3 significant accumulation
            elif cum[i] > 2500 and net6[i] > 600:
                fluid_state.append(2)       # FS-2 increasing positive balance
            elif cum[i] > 2500 or uo6[i] < 35:
                fluid_state.append(1)       # FS-1 monitor closely
            else:
                fluid_state.append(0)       # FS-0 stable

    out["y_det6"] = det6
    out["y_det12"] = det12
    out["y_det24"] = det24
    out["y_recovery"] = recovery
    out["y_abx"] = abx_resp
    out["y_fluid"] = fluid_state
    return out


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in
            ("patient_id", "hour", "state", "y_det6", "y_det12", "y_det24",
             "y_recovery", "y_abx", "y_fluid")]


if __name__ == "__main__":
    from pathlib import Path
    d = Path(__file__).parent / "data"
    vitals = pd.read_csv(d / "timeseries.csv")
    patients = pd.read_csv(d / "patients.csv")
    abx = pd.read_csv(d / "antibiotics.csv")
    feats = build_features(vitals, patients, abx)
    feats = build_targets(feats, vitals)
    feats.to_parquet(d / "features.parquet", index=False)
    print(f"features: {feats.shape}, cols={len(feature_columns(feats))}")
    for t in ["state", "y_det6", "y_recovery", "y_abx", "y_fluid"]:
        print(t, dict(feats[t].value_counts().sort_index()))
