# MedVault — Limitations

**This is a research/education prototype. It has no clinical validation and
must not be used for patient care.**

## Data
- **Synthetic data**: labels derive from a simulated latent severity process,
  so the task is easier and cleaner than reality; reported metrics
  (macro-F1 0.73–0.98) will not transfer to real ICU data. Feature importances
  also mirror simulator structure — e.g. fluid input ranks highly partly
  because the simulator couples resuscitation volume to severity.
- No comorbidities, medications other than antibiotics, ventilation,
  vasopressor dosing, or source-control events are modeled.
- Single simulated "institution": no cross-site heterogeneity, device
  differences, or documentation-practice variation.

## Labels
- Ground-truth states are rule-derived from the latent process, not clinician
  adjudication; boundary hours between states are inherently noisy.
- Antibiotic-response and fluid-status labels encode simplified physiology
  (e.g. no distinction between distributive and cardiogenic shock).

## Modeling
- Treatment confounding: models observe treated trajectories only and cannot
  answer counterfactuals ("what if antibiotics had started earlier").
- Calibration is checked only via Brier score on the binary task; multi-class
  probabilities are not recalibrated.
- No prospective or temporal-drift validation; a deployed system would need
  drift monitoring and periodic retraining.
- SHAP contributions describe model behaviour, not clinical causation.

## Composite risk score, timeline and simulation (Review 3)
- The **MedVault Composite Risk Score** is a hand-weighted summary of the
  model outputs. Its weights, class severities and band limits (25 / 50 / 75)
  are design choices; none was fitted to or validated against outcomes. It is
  not comparable to SOFA, NEWS or any validated score.
- Its components are correlated (all derive from the same physiology), so a
  high score is one summary of the models, not several independent signals.
- Data quality qualifies the score in words but does not change it; a score
  built on stale labs looks the same as one built on fresh ones.
- Timeline thresholds (e.g. MAP < 65 mmHg, lactate step ≥ 0.6 mmol/L) are
  illustrative event rules, not alarm settings.
- The **scenario simulation** moves one latent severity value and derives
  every observable from it with population baselines, so simulated patients
  are simpler and more coherent than the seeded ones, which are themselves
  simpler than real patients. It demonstrates the pipeline; it is not a
  physiological model and says nothing about what a real patient would do.
- The overall **data-quality score** is nearly constant on this dataset
  (71–76 %) because lab sampling cadence dominates it; the warnings and lab
  timeliness carry most of the information.

## Clinical safety
- False negatives (missed deterioration) remain possible; the system is
  decision support, not a safety net.
- False positives cause alarm fatigue; thresholds (0.5/0.75) are illustrative
  and untuned against a real alarm-burden budget.
- The 8-state framework is a research abstraction, not a validated staging
  system (unlike SOFA/qSOFA which a production system should also report).

## Engineering
- SQLite and a dev JWT secret are for local demo; production needs PostgreSQL,
  secret management, HTTPS, audit logging, and rate limiting.
- The live simulation reuses a simplified severity-inversion heuristic; it is
  demonstration machinery, clearly labeled in the UI.

## Right-censoring at the latest hour (important for demos)

Recovery and antibiotic response are forward-looking (12 h). Rows within 12 h
of a record's end have no observable outcome window, so they carry no valid
label and are excluded from training (17.0% of rows) rather than given a
clamped, fake one.

The consequence is visible in the UI: the dashboard shows each patient's
**latest** hour, which is always such a row. Those predictions are genuine
extrapolations on a feature distribution the model never saw supervised, and
they skew conservative — RT-0 (improving) and RT-4 (worsening) are rarely
predicted at the final hour even though both are well represented in training.
Mid-stay predictions, visible on the recovery-trajectory chart and via the
live simulation, are the better guide to real model behaviour.

This is a property of forward-looking labels on finite records, not a bug, and
it would also occur on MIMIC-IV. Addressing it properly would require either a
survival-style model that handles censoring directly, or restricting the
display to hours with a complete outcome window.

## Residual label correlation

The five tasks are derived from disjoint observable subsystems, but the
subsystems themselves covary in the underlying physiology (as they do in real
patients). Pairwise normalized mutual information sits around 0.24–0.34 — much
lower than the 0.479 measured when recovery and antibiotic response were both
slope transforms of one latent variable, but not zero. Claims of fully
independent tasks would be overstated; see `error_analysis.md` for the numbers.
