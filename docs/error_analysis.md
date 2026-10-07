# MedVault — Error Analysis

Computed on the held-out patient-level test set (42 patients). Real model outputs on synthetic data.

## Label independence

Each task derives from a disjoint observable subsystem (`label_definitions.md`).
Normalized mutual information between label pairs (censored rows excluded):

| Pair | NMI |
|---|---|
| RT vs AR | 0.339 |
| RT vs FS | 0.341 |
| AR vs FS | 0.342 |
| RT vs 6h deterioration | 0.242 |

Before the labels were separated, RT vs AR measured 0.479 — both were slope transforms
of one latent severity variable. Residual correlation is expected: real clinical variables
covary. RT vs deterioration rose from 0.137 because recovery is now forward-looking like
deterioration; that trade-off is reported rather than hidden.

## Right-censoring

Rows within 12 h of a record's end have no observable outcome window. They are marked -1
and excluded from every split (17.0% of rows) instead of being given a clamped, fake label.
**Consequence worth knowing:** the dashboard shows each patient's latest hour, which is
always a censored row. Those predictions are genuine extrapolations the model was never
trained on, and they skew conservative — RT-0 and RT-4 are rarely predicted at the final
hour even though both are well represented in training. Mid-stay predictions are the
better guide to real model behaviour.

## Recovery (random_forest)

- Error rate 28.8%; mean confidence 0.51 on errors vs 0.66 on correct rows — misclassifications are systematically less confident, usable as an uncertainty signal.
- Most common confusions (true → predicted): RT-1 Stable → RT-2 Slow recovery (119); RT-2 Slow recovery → RT-1 Stable (108); RT-1 Stable → RT-4 Worsening (76); RT-4 Worsening → RT-3 Persistent concern (76)
- Recovery is the hardest task by design: it forecasts the organ-dysfunction trajectory 12 h ahead rather than describing the current one. Errors concentrate on the RT-1/RT-2 boundary, which is a genuinely narrow distinction.

## Antibiotic Response (random_forest)

- Error rate 9.3%; mean confidence 0.56 on errors vs 0.88 on correct rows — misclassifications are systematically less confident, usable as an uncertainty signal.
- Most common confusions (true → predicted): AR-3 Poor response → AR-0 Improving (75); AR-0 Improving → AR-4 Worsening (30); AR-2 Uncertain → AR-1 Stable / no clear change (19); AR-2 Uncertain → AR-0 Improving (18)
- AR-2 (uncertain/insufficient) dominates because it covers every pre-antibiotic and early-exposure hour; the informative classes are the post-4h ones.

## Fluid Status (lightgbm)

- Error rate 3.0%; mean confidence 0.84 on errors vs 0.99 on correct rows — misclassifications are systematically less confident, usable as an uncertainty signal.
- Most common confusions (true → predicted): FS-3 Significant accumulation concern → FS-1 Monitor closely (15); FS-3 Significant accumulation concern → FS-2 Increasing positive balance (14); FS-0 Stable fluid trajectory → FS-5 Insufficient data (14); FS-2 Increasing positive balance → FS-3 Significant accumulation concern (12)

## Deterioration 6H (random_forest)

- False positives 314 (10.9%); false negatives 145 (5.0%).
- False-positives by archetype: sepsis_nonresponder (30%), deteriorating (23%), sepsis_responder (16%); mean confidence 0.67.
- False-negatives by archetype: sepsis_nonresponder (29%), deteriorating (29%), sepsis_responder (21%); mean confidence 0.65.
- Errors cluster at severity-trend inflection points: the label flips before observable trends complete, so the model is 'late' at turning points.

## Uncertain cases

Rows with <6 h of data are labeled insufficient (AR-2/FS-5/RT-5) and the state engine returns
'Insufficient Data' rather than forcing a prediction. Hours with volatile but trendless infection
markers are labeled AR-2; these carry the lowest per-class probabilities and are surfaced with
reduced-confidence framing in the UI.
