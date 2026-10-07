# MedVault — Label Definitions

All labels below are **research-derived proxy labels**. They are NOT clinical
diagnoses.

Each task is derived from a **distinct observable subsystem**, so the labels
are not four transformations of one latent variable:

| Task | Derived from | Direction |
|---|---|---|
| Recovery (RT) | organ-dysfunction score: MAP, creatinine, urine output, bilirubin, platelets, SpO2 | **forward 12 h** |
| Antibiotic response (AR) | infection markers: temperature, WBC, lactate (gated on antibiotic exposure) | **forward 12 h** |
| Fluid status (FS) | fluid/renal observables: cumulative balance, urine output, creatinine trend, MAP | current state |
| Deterioration | composite latent severity `s(t)` | forward 6 / 12 / 24 h |

The organ-dysfunction and infection-marker scores use **disjoint variable
sets** by construction (`ml/features.py`: `organ_dysfunction_score`,
`infection_marker_score`). Recovery and antibiotic response look **forward**,
so the models must predict a future trajectory rather than recompute a
concurrent one. All future-looking values are targets only, never features.

Measured effect (normalized mutual information, full dataset): RT vs AR fell
from **0.479 to 0.311** when the labels were separated. RT vs 6h deterioration
rose from 0.137 to 0.226, because recovery is now forward-looking like
deterioration — an accepted trade-off, reported in `error_analysis.md` rather
than hidden. Residual correlation is expected: real clinical variables covary.

With a real dataset (MIMIC-IV) the same definitions map onto SOFA components,
culture clearance and charted fluid records — the derivation logic is unchanged;
only the source of the observables differs.

Three layers are always distinguished:

1. **Ground-truth label** — derived at dataset-build time by the rules below
   (`ml/features.py:build_targets`), using future information *only for the
   target*, never for features.
2. **Model prediction** — a trained classifier's probabilistic output.
3. **Dashboard interpretation** — the rule-based Patient State Engine
   (`backend/app/services/state_engine.py`), which combines model outputs.

## Cohort & windows

- Inclusion: all simulated ICU stays (48–96 h of hourly data).
- Observation window: all data up to the prediction hour (causal features).
- Prediction windows: 6 h / 12 h / 24 h for deterioration; 12 h **forward**
  window for recovery and antibiotic response; fluid status is current-state.
- Missing-data rule: rows with < 6 h of history receive
  insufficient-data labels (AR-2 / FS-5 / RT-5) and the state engine returns
  "Insufficient Data" instead of forcing a prediction.

## Derived scores

**Organ-dysfunction score** `organ(t)` ∈ [0,1] — weighted sum of clipped,
normalized components (4h centered smoothing): cardiovascular MAP (0.28),
renal creatinine + urine output (0.28), hepatic bilirubin (0.16), coagulation
platelets (0.14), respiratory SpO2 (0.14). Higher = worse.

**Infection-marker score** `infl(t)` ∈ [0,1] — |temperature − 37 °C| (0.34),
|WBC − 7.5| (0.30), lactate (0.36). Disjoint from the organ components above.

## Recovery trajectory (RT) — 6 classes · forward 12 h

`d_organ = organ(t+12) − organ(t)` (clamped at the end of the stay).

| Label | Rule (first match) |
|---|---|
| RT-5 Insufficient evidence | `< 6 h` of data |
| RT-0 Improving | `d_organ < −0.08` |
| RT-4 Worsening | `d_organ > 0.06` |
| RT-2 Slow recovery | `d_organ < −0.02` |
| RT-3 Persistent concern | flat trend and `organ(t) > 0.40` |
| RT-1 Stable | otherwise |

This is a genuine forward prediction: the model sees only past data and must
anticipate the organ-dysfunction trajectory 12 h ahead.

## Antibiotic response (AR) — 5 classes · forward 12 h

Evaluated only in the context of antibiotic exposure. `h` = hours since
antibiotic initiation; `d_infl = infl(t+12) − infl(t)`; `vol` = 12h rolling
std of `infl`.

| Label | Rule (first match) |
|---|---|
| AR-2 Uncertain | not on antibiotics, or `h < 4`, or (`vol > 0.10` and `|d_infl| < 0.03`) — contradictory/insufficient |
| AR-0 Improving | `d_infl < −0.06` |
| AR-4 Worsening | `d_infl > 0.04` |
| AR-3 Poor response | flat trend and `infl(t) > 0.45` (no expected improvement) |
| AR-1 Stable / no clear change | otherwise |

These states describe an **observed trajectory during treatment exposure** —
they do not establish that the antibiotic caused the change, nor
microbiological eradication.

## Fluid status (FS) — 6 classes · current state

`cum` = cumulative net balance (mL); `net6` = 6h net balance; `uo6` = 6h mean
urine output (mL/h); `cs` = 12h mean creatinine slope. No severity term.

| Label | Rule (first match) |
|---|---|
| FS-5 Insufficient data | `< 6 h` of records |
| FS-4 Possible inadequate hemodynamic response | `uo6 < 25` and `MAP < 66` |
| FS-3 Significant accumulation concern | `cum > 4000` and (`uo6 < 40` or `cs > 0.004`) |
| FS-2 Increasing positive balance | `cum > 2500` and `net6 > 600` |
| FS-1 Monitor closely | `cum > 2500` or `uo6 < 35` |
| FS-0 Stable fluid trajectory | otherwise |

Fluid status is a **current-state characterization**, not a forward
prediction — cumulative balance is a measured quantity, not a forecast.
Monitoring categories only — never treatment instructions.

## Deterioration (binary, 3 horizons)

`y_det{k} = 1` iff `s(t+k) − s(t) > 0.08` OR (`s(t+k) > 0.6` and rising), for
k ∈ {6, 12, 24}. Future severity is used **only** to build these targets.

## Patient State Engine (STATE 0–8) — dashboard interpretation

The engine is **recovery-led**. The recovery trajectory (RT) is the primary
driver of the overall state; antibiotic response (AR) and fluid status (FS)
refine it; the 6h deterioration probability (`p_det`) acts as a **supporting
signal** that corroborates or escalates — it is not the headline classifier.

Deterministic priority rules over model outputs (first match wins):

| Priority | State | Condition |
|---|---|---|
| 0 | Insufficient Data | < 6 h of observations |
| 1 | 7 High-Risk Clinical Trajectory | RT-4 **and** (AR-4 or `p_det ≥ 0.6`) |
| 2 | 7 High-Risk Clinical Trajectory | `p_det ≥ 0.85` — safety escalation (see below) |
| 3 | 6 Poor Recovery Trajectory | RT-3 or RT-4 |
| 4 | 5 Fluid Status Concern | FS-3 or FS-4 |
| 5 | 3 Persistent Concern | AR-3 |
| 6 | 4 Treatment Response Uncertain | AR-2 and RT ≠ RT-0 |
| 7 | 8 Improving / Recovery | RT-0 |
| 8 | 1 Treatment Response | RT-2, or AR-0 |
| 9 | 2 Monitoring Required | FS-1/FS-2, or `p_det ≥ 0.4` |
| 10 | 0 Stable | otherwise |

Additionally, whenever the resolved state is neither 7 nor 2 and `p_det ≥ 0.5`,
a supporting-signal line is appended to the state's reasons so a non-trivial
short-term risk is never silently dropped from the display.

### Safety escalation (priority 2)

The `p_det ≥ 0.85` rule is retained deliberately. Making recovery the narrative
focus must not allow a very high short-term deterioration risk to be presented
as an improving patient. This is the one place where the deterioration model
can override the recovery-led ordering.

## Treatment Response Index

Research-derived composite (0–100): a **weighted** combination of four
sub-scores, each the probability-weighted favourability of one model's output
distribution (class weights in `state_engine.py`).

| Component | Weight |
|---|---|
| Recovery trajectory | 0.40 |
| Antibiotic response | 0.25 |
| Fluid trajectory | 0.20 |
| Stability (1 − `p_det`) | 0.15 |

Recovery is weighted highest, consistent with the recovery-led framing;
deterioration contributes only as a supporting term. Weights are renormalized
over whichever components are available, so a missing model does not distort
the index. **Not a validated clinical score** and labeled as such wherever
displayed.

## Recovery score (time series)

The longitudinal recovery chart plots a 0–100 score computed as the
probability-weighted favourability of the recovery model's output distribution
using `RECOVERY_WEIGHTS` (RT-0 = 1.0, RT-1 = 0.7, RT-2 = 0.55, RT-3 = 0.2,
RT-4 = 0.0, RT-5 = 0.5 for insufficient evidence). It is derived directly from
model output — no invented values — and shares its weights with the TRI
recovery component so the definition lives in one place.
