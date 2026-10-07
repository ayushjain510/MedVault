# MedVault — ML Methodology

## 1. Problem framing

Sepsis is a dynamic condition; single-timepoint classification is clinically
inadequate. MedVault therefore decomposes monitoring into **seven specialized
prediction tasks**, each answered by its own model over shared temporal
features, combined by a recovery-led orchestration layer:

| # | Task | Role | Horizon | Label source | Type |
|---|------|------|---------|--------------|------|
| 1 | Recovery trajectory (RT) | **primary** | **+12 h** | organ-dysfunction score | multi-class (6) |
| 2 | Antibiotic response (AR) | treatment module | **+12 h** | infection markers | multi-class (5) |
| 3 | Fluid status (FS) | treatment module | current | fluid / renal observables | multi-class (6) |
| 4 | Sepsis state | context | current | composite severity | multi-class (8) |
| 5–7 | Deterioration 6 / 12 / 24 h | supporting | +6/12/24 h | composite severity | binary |

Classes: RT-0 Improving · RT-1 Stable · RT-2 Slow recovery · RT-3 Persistent
concern · RT-4 Worsening · RT-5 Insufficient evidence. AR-0 Improving · AR-1
Stable / no clear change · AR-2 Uncertain · AR-3 Poor response · AR-4
Worsening. FS-0 Stable · FS-1 Monitor closely · FS-2 Increasing positive
balance · FS-3 Significant accumulation concern · FS-4 Possible inadequate
hemodynamic response · FS-5 Insufficient data.

Each task draws its label from a **distinct observable subsystem**, so the
targets are not repeated transformations of one latent variable, and the two
treatment-relevant tasks look **forward 12 h** — the models predict a future
trajectory rather than recompute a concurrent one.

The platform is **recovery-centric**: the recovery trajectory is the headline
output, the treatment modules (AR, FS) refine it, and the deterioration
horizons act as corroborating evidence rather than the primary classification.
Exact class rules, the recovery-led state-engine priority order, and the one
retained safety escalation are documented in `label_definitions.md`.

Predicted states are **AI risk assessments, not diagnoses**. The UI carries a
permanent disclaimer and alerts never issue treatment orders.

## 2. Dataset

Real ICU datasets (MIMIC-IV, PhysioNet Sepsis Challenge, eICU) require
credentialed access agreements; this prototype instead uses a **clearly-labeled
synthetic dataset** (`ml/data_simulator.py`, seed 42): 240 patients, 48–96
hourly observations each (~17k rows), drawn from 7 clinically-motivated
trajectory archetypes (stable, at-risk, antibiotic responder, slow responder,
non-responder, progressive deterioration, fluid overload). A latent severity
process drives physiologically-plausible vitals/labs (tachycardia,
hypotension, lactate rise, oliguria, thrombocytopenia, creatinine drift) with
AR(1) correlated noise and realistic lab sampling gaps (labs every 4–8 h, 3%
missing vitals). The pipeline is dataset-agnostic: substituting MIMIC-IV means
re-implementing only the loader; features, training and serving are unchanged.

## 3. Temporal features (227 columns)

Per signal (7 vitals, 5 labs, 3 fluid variables): current value, rolling
mean (3/6/12/24 h), min/max/std (6/24 h), linear-trend slopes (6/12 h), 3-h
delta. Plus: shock index, cumulative and 6-h net fluid balance, lab
missingness indicators, hours-since-last-measurement, age, sex, antibiotic
exposure and hours since initiation. All windows end at the current hour —
**features are strictly causal** (verified by an automated test that removes
future rows and asserts identical features).

## 4. Leakage prevention

- **Patient-level split** 70/15/15 (train/val/test), stratified by archetype;
  asserted disjoint. No patient contributes rows to more than one split.
- The latent `severity` variable and all `y_*` targets are excluded from
  features (tested).
- Imputation and scaling are inside sklearn Pipelines — **fitted on train
  only**.
- Class imbalance handled by class weighting / `scale_pos_weight`, never by
  resampling across timelines.
- Future-looking labels are targets ONLY, never features. This now covers the
  recovery (organ trajectory +12 h), antibiotic response (infection markers
  +12 h) and deterioration (+6/12/24 h) tasks. Features are strictly causal:
  every window ends at the prediction hour, enforced by an automated truncation
  test (`tests/test_ml.py`).

## 5. Models compared

Per task: **Logistic Regression** (interpretable baseline, balanced class
weights, C=0.1), **Random Forest** (200 trees, depth 12), **XGBoost** (300
trees, depth 5, lr 0.08) and **LightGBM** (300 trees, depth 6, lr 0.08,
balanced class weights). An LSTM/GRU was considered and **deliberately not
used**: the effective sample size is 240 patients — far below the regime where
sequence models outperform gradient boosting over engineered temporal windows —
and boosting gives better calibration and SHAP interpretability at this scale.

## 6. Selection criterion

`0.55 × macro-recall + 0.45 × macro-F1` on the validation set. Accuracy is
reported but never used for selection: in a safety context a **false negative
(a missed worsening trajectory) is costlier than a false positive**
(unnecessary review), so sensitivity to minority high-risk classes dominates.

Winners (four candidates compared per task — Logistic Regression, Random
Forest, XGBoost, LightGBM):

| Task | Selected |
|---|---|
| Recovery trajectory | Random Forest |
| Antibiotic response | Random Forest |
| Fluid status | LightGBM |
| Sepsis state | XGBoost |
| Deterioration 6h / 12h / 24h | Random Forest |

(This table is checked against `ml/models/report.json`, the output of
`ml/train.py`, which is the source of truth; an earlier revision of this
document listed XGBoost for recovery and Logistic Regression for antibiotic
response, which did not match the evaluation output.)

The margins are small on the forward-looking tasks. For antibiotic response,
Random Forest (validation macro F1 0.836, macro recall 0.850) is selected
over XGBoost (0.837 / 0.841): XGBoost has the marginally higher F1, but the
selection score weights recall more heavily. For recovery, Random Forest
(0.637 / 0.682) leads XGBoost (0.632 / 0.659). Gradient boosting wins only
two of the seven tasks, which is why all four candidates are compared per
task instead of assuming a gradient-boosting winner.

Full validation/test metrics, confusion matrices, ROC-AUC/PR-AUC/Brier and
calibration curves for the three binary horizons, and per-class distributions
are in `ml/models/report.json`, `model_evaluation.md`, and on the Model Lab
page.

## 7. Explainability

- **Global**: mean |SHAP| (TreeExplainer) per model in
  `ml/models/global_importance.json`.
- **Local**: per-patient, per-task contributions computed on demand
  (`/api/explanations/{pid}`) — SHAP for tree models, coefficient×standardized
  value for the logistic pipeline — rendered as signed factor bars with the
  caveat that contributions reflect model behaviour, not verified causation.

## 8. Missing data

Labs are forward-filled per patient (clinically justified: the last measured
value stands until re-measured) **plus** missingness indicators and
hours-since-measurement features so models can learn from sampling patterns;
remaining gaps use train-fitted median imputation. Vitals gaps (3%) are
forward-filled within patient only.
