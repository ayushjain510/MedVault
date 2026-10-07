# MedVault — Ethics

## Privacy & data governance
- All shipped data is synthetic; no real patient information exists in this
  repository. The UI labels it "SYNTHETIC DEMONSTRATION DATA" permanently.
- MIMIC-IV is credentialed-access data: using it requires a PhysioNet account,
  CITI human-subjects training, and a signed Data Use Agreement. Derived data
  must not be redistributed; models trained on it should be checked for
  memorization before sharing.
- Privacy by design: anonymized IDs only; no free-text notes; the API never
  exposes fields beyond what each page needs; role-based access limits model
  internals to researchers.

## Clinical responsibility & human oversight
- The system is decision support. Alerts request clinician review; they never
  order fluids, select antibiotics, or state a diagnosis. This boundary is
  enforced by an automated test on alert text.
- **Automation bias** is a real risk: clinicians may over-trust confident
  model output. Mitigations here: probabilities always shown as "model
  probability — not certainty", explanations shown with a non-causality
  caveat, insufficient-data states returned instead of forced predictions.
- **False negatives** (missed deterioration) can delay review; **false
  positives** cause alarm fatigue that erodes trust in all alerts. Model
  selection therefore weights recall, and alert thresholds are tiered — but
  neither is clinically tuned; deployment would require a prospective
  alarm-burden study.

## Bias & fairness
- The synthetic cohort has no ethnicity, insurance, or language variables, so
  demographic bias cannot be measured here — that is a limitation, not an
  absence of risk. On real data, subgroup performance (age, sex, ethnicity,
  admission source) must be reported before any use.
- Sampling-frequency bias: sicker patients are measured more often; models can
  learn measurement patterns rather than physiology. Missingness indicators
  make this explicit rather than hidden, but it must be audited on real data.

## Dataset shift & validation
- Models are valid only for data resembling training data. Institution,
  device, documentation-practice and temporal drift all degrade performance
  silently; deployment requires drift monitoring and scheduled revalidation.
- No external validation or prospective clinical validation has been
  performed. Any performance claim in this repository refers to the synthetic
  held-out test set only.
