"""Patient State Engine — deterministic combination of model outputs.

This layer is RULE-BASED, not ML. It maps the five model outputs plus a data-
sufficiency check onto the overall STATE 0-8 framework. Rules are documented
in docs/label_definitions.md and are deliberately kept separate from the ML
predictions so the dashboard can always distinguish:
  ground-truth label  vs  model prediction  vs  dashboard interpretation.
"""

STATES = {
    0: "Stable",
    1: "Treatment Response",
    2: "Monitoring Required",
    3: "Persistent Concern",
    4: "Treatment Response Uncertain",
    5: "Fluid Status Concern",
    6: "Poor Recovery Trajectory",
    7: "High-Risk Clinical Trajectory",
    8: "Improving / Recovery",
}

STATE_TONE = {0: "green", 1: "blue", 2: "yellow", 3: "orange", 4: "yellow",
              5: "orange", 6: "orange", 7: "red", 8: "green"}


def _cls(pred: dict | None) -> int | None:
    return pred.get("predicted_class") if pred else None


def compute_state(preds: dict, hours_of_data: int) -> dict:
    """preds: {task: {predicted_class, predicted_label, probability, probabilities}}.

    RECOVERY-LED ordering. The recovery trajectory (RT) is the primary driver
    of the overall state; antibiotic response (AR) and fluid status (FS) refine
    it; the 6h deterioration probability acts as a SUPPORTING signal that can
    escalate or corroborate, not as the headline classifier.

    Priority order (first match wins):
      INSUFFICIENT  <6h of observations
      STATE 7       RT-4 worsening corroborated by AR-4 or p_det >= 0.6
                    — plus a safety net: p_det >= 0.85 escalates on its own
      STATE 6       RT-3 / RT-4 (poor recovery trajectory)
      STATE 5       fluid FS-3 or FS-4
      STATE 3       antibiotic AR-3 (poor response)
      STATE 4       antibiotic AR-2 (uncertain) while recovery is not improving
      STATE 8       recovery RT-0 improving
      STATE 1       recovery RT-2 slow recovery, or AR-0 improving on treatment
      STATE 2       fluid FS-1/FS-2, or a non-trivial deterioration probability
      STATE 0       otherwise

    Safety note: the p_det >= 0.85 escalation is retained deliberately. Making
    recovery the narrative focus must not let a very high short-term risk be
    presented as an improving patient.
    """
    det = preds.get("deterioration_6h", {})
    p_det = det.get("probabilities", {}).get("Deterioration ≤6h", 0.0)
    ar = _cls(preds.get("antibiotic_response"))
    fs = _cls(preds.get("fluid_status"))
    rt = _cls(preds.get("recovery"))

    reasons = []
    if hours_of_data < 6:
        return {"state": None, "label": "Insufficient Data", "tone": "gray",
                "reasons": [f"Only {hours_of_data}h of observations; the state engine "
                            "requires at least 6h."],
                "rule_based": True}

    if rt == 4 and (ar == 4 or p_det >= 0.6):
        state = 7
        reasons.append("RT-4 Worsening recovery trajectory")
        reasons.append("Corroborated by worsening antibiotic response" if ar == 4
                       else f"Supporting signal: {p_det:.0%} 6h deterioration probability")
    elif p_det >= 0.85:
        state = 7
        reasons.append(f"Safety escalation: {p_det:.0%} 6h deterioration probability")
    elif rt in (3, 4):
        state = 6
        reasons.append(preds["recovery"]["predicted_label"])
    elif fs in (3, 4):
        state = 5
        reasons.append(preds["fluid_status"]["predicted_label"])
    elif ar == 3:
        state = 3
        reasons.append("AR-3 Poor response to antimicrobial treatment trajectory")
    elif ar == 2 and rt != 0:
        state = 4
        reasons.append("AR-2 Uncertain antibiotic response without an improving recovery trajectory")
    elif rt == 0:
        state = 8
        reasons.append("RT-0 Improving recovery trajectory")
    elif rt == 2 or ar == 0:
        state = 1
        reasons.append("RT-2 Slow recovery trajectory" if rt == 2
                       else "AR-0 Improving response after treatment initiation")
    elif fs in (1, 2) or p_det >= 0.4:
        state = 2
        reasons.append(preds["fluid_status"]["predicted_label"] if fs in (1, 2)
                       else f"Supporting signal: {p_det:.0%} 6h deterioration probability")
    else:
        state = 0
        reasons.append("No concerning model outputs")

    if state not in (7, 2) and p_det >= 0.5:
        reasons.append(f"Supporting signal: {p_det:.0%} 6h deterioration probability")

    return {"state": state, "label": STATES[state], "tone": STATE_TONE[state],
            "reasons": reasons, "rule_based": True}


# Favourability weight per class index (1 = fully favourable). Recovery weights
# are reused by the recovery-score time series so the definition lives in one place.
RECOVERY_WEIGHTS = [1.0, 0.7, 0.55, 0.2, 0.0, 0.5]   # RT-0 .. RT-5
ABX_WEIGHTS = [1.0, 0.6, 0.5, 0.15, 0.0]             # AR-0 .. AR-4
FLUID_WEIGHTS = [1.0, 0.7, 0.4, 0.1, 0.1, 0.5]       # FS-0 .. FS-5

# Recovery is the primary focus; deterioration contributes as a supporting signal.
TRI_WEIGHTS = {"recovery_trajectory": 0.40, "antibiotic_response": 0.25,
               "fluid_trajectory": 0.20, "stability_6h": 0.15}


def recovery_score(probabilities: dict) -> int:
    """0-100 recovery-trajectory score from an RT probability distribution.

    Derived directly from model output — no invented numbers.
    """
    total = 0.0
    for i, c in enumerate(probabilities):
        w = RECOVERY_WEIGHTS[i] if i < len(RECOVERY_WEIGHTS) else 0.0
        total += probabilities[c] * w
    return round(total * 100)


def treatment_response_index(preds: dict) -> dict | None:
    """Research-derived composite indicator (0-100), NOT a validated score.

    Sub-scores map each model's probability mass toward favourable classes, then
    combine with recovery weighted highest (see TRI_WEIGHTS).
    """
    def favourable(task, weights):
        pred = preds.get(task)
        if not pred:
            return None
        probs = pred.get("probabilities", {})
        classes = list(probs.keys())
        total = 0.0
        for i, c in enumerate(classes):
            w = weights[i] if i < len(weights) else 0.0
            total += probs[c] * w
        return round(total * 100)

    abx = favourable("antibiotic_response", ABX_WEIGHTS)
    fluid = favourable("fluid_status", FLUID_WEIGHTS)
    rec = favourable("recovery", RECOVERY_WEIGHTS)
    det = preds.get("deterioration_6h", {})
    p_det = det.get("probabilities", {}).get("Deterioration ≤6h")
    stab = round((1 - p_det) * 100) if p_det is not None else None

    components = {"recovery_trajectory": rec, "antibiotic_response": abx,
                  "fluid_trajectory": fluid, "stability_6h": stab}
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return None
    # renormalize weights over whichever components are available
    wsum = sum(TRI_WEIGHTS[k] for k in available)
    index = round(sum(v * TRI_WEIGHTS[k] for k, v in available.items()) / wsum)
    return {"index": index, "components": components, "weights": TRI_WEIGHTS,
            "note": ("Research-derived composite indicator — not a validated clinical "
                     "score. Recovery trajectory is weighted highest (0.40); the 6h "
                     "deterioration probability contributes as a supporting signal (0.15).")}
