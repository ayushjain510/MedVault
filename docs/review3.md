# MedVault — Review 3 Architecture

Review 3 turns the ML demo into one connected monitoring platform:

```text
secure access → patient data → ML predictions → explainability →
risk assessment → timeline → alerts → simulation → updated predictions
```

Five additions, all built on the existing pipeline (no model was replaced or
retrained differently, and no number shown in the UI is hardcoded):

| | Feature | Backend | Frontend |
|---|---|---|---|
| A | Patient Risk Score | `services/risk.py` | `components/RiskCard.tsx`, Risk Monitoring page |
| B | Clinical Timeline | `services/timeline.py` | `components/ClinicalTimeline.tsx` |
| C | Scenario Simulation | `services/simulator.py` (extended) | `components/SimulationPanel.tsx` |
| D | Data Quality Monitoring | `services/analytics.py` (extended) | `components/DataQualityCard.tsx` |
| E | Role-Based Services | `services/permissions.py`, `admin.py`, `services/dashboards.py`, `services/audit.py` | role dashboards, `nav.ts`, admin pages |

> Everything here runs on **synthetic data**. MedVault is an academic
> research prototype: predictions are not diagnoses, the risk score is not a
> validated clinical score, the simulation is synthetic, alerts are
> decision-support indicators, and the system never prescribes treatment.

---

## A. Patient Risk Score

**Purpose.** One high-level number (0–100) and level per patient that
summarises what the seven models, the state engine and the recent trend are
saying, with the contributors visible. Labelled everywhere as *MedVault
Composite Risk Score — research / prototype indicator, not a validated
clinical score*.

**Inputs and scoring.** Six components, each with a fixed maximum (sum 100).
Each uses the model's **full probability distribution**, not the arg-max
label, so the score moves smoothly instead of jumping when a class flips.

| Component | Max | How the points are computed |
|---|---|---|
| Deterioration risk | 35 | `35 × (0.5·p₆ₕ + 0.3·p₁₂ₕ + 0.2·p₂₄ₕ)` — the three deterioration models |
| Sepsis state | 20 | `20 × Σ p(class) · severity(class)`; severities: Stable 0, Recovery 0.1, At Risk 0.35, Treatment Response 0.35, Active Sepsis 0.6, Non-responding 0.8, Severe/Deteriorating 0.9, Escalation 1.0 |
| Recovery trajectory | 20 | `20 × (1 − favourability)`, using the existing `RECOVERY_WEIGHTS` (the same weights as the recovery score) |
| Antibiotic response | 10 | `10 × (1 − favourability)`, existing `ABX_WEIGHTS` |
| Fluid status | 8 | `8 × (1 − favourability)`, existing `FLUID_WEIGHTS` |
| Recent physiological trend | 7 | `7 × clip(−trend / 3, 0, 1)`, where `trend` is the favourability score of the existing "What changed?" analysis (last 6 h vs previous 6 h) |

`score = round(Σ points)`. Rules around it:

- **Missing input** → that component is left out and the rest are rescaled
  (`100 × Σ points / Σ max of available`); the response sets `renormalised`.
- **Under 6 h of data** → no score; level `INSUFFICIENT DATA`.
- **State-engine floor** → while the rule-based engine reports STATE 7
  (High-Risk Clinical Trajectory) the score is not shown below 50 (HIGH). The
  response sets `floor_applied` and still returns `raw_score`. On the seeded
  data this applies to about 1.4 % of scored patient-hours.

**Risk levels.** `0–24 LOW · 25–49 MODERATE · 50–74 HIGH · 75–100 CRITICAL`.
On the seeded cohort (latest hour) this gives 135 LOW / 53 MODERATE / 47 HIGH
/ 5 CRITICAL, and the mean score orders the generator archetypes as expected
(stable 16 → sepsis non-responder 67), which is the only sanity check a
synthetic dataset allows.

**Storage.** Scores are written to `risk_scores` for every patient-hour at
seed time and for each simulated hour, by the same `compute_risk()` that
serves the API. Lists, dashboards and the timeline read the stored rows; the
patient endpoint recomputes live and a test asserts the two agree.

**Risk and data quality.** The risk response carries a `data_quality` block
with a plain-language caveat ("…interpreted with caution because creatinine
has not been measured recently"). Data quality **never changes the score**
(`score_adjusted: false`); it only qualifies it.

**Limitations.** Weights and severities are design choices, not fitted or
validated against outcomes. The components are correlated (all derive from
the same physiology), so the score is a summary, not independent evidence.
It inherits every limitation of the underlying models and of synthetic data.

## B. Clinical Timeline

`GET /api/patients/{id}/timeline` (extended, same URL as before). Nothing is
stored as a "timeline": events are aggregated on request from the existing
tables, sorted by hour (cause before consequence within an hour).

| Event type | Source | Rule |
|---|---|---|
| `admission` | `patients` | hour 0 |
| `antibiotic` | `antibiotic_records` | treatment start |
| `culture` | `antibiotic_records` | culture result at the hour it becomes available |
| `vital` | `vitals` | onset / resolution of a threshold on the 3 h mean (MAP < 65, SpO₂ < 92, HR > 110, RR > 24, temperature ≥ 38.3), with hysteresis |
| `lab` | `vitals` | step change vs the last *reported* value (e.g. lactate ≥ 0.6 mmol/L and ≥ 25 %) — "Lactate increased from 1.9 to 2.8 mmol/L" |
| `fluid` | `vitals` | cumulative balance passing +2,500 / +4,000 mL; 6 h mean urine output < 30 mL/h |
| `state_change` | `predictions` → state engine | rule-based state changes |
| `prediction` | `predictions` | sepsis-state classifier changes |
| `risk_change` | `risk_scores` | risk-band crossings |
| `alert` | `alerts` | the same alert on consecutive hours is one event with an "active until" hour |
| `simulation` | `simulation_events` | consecutive simulated hours under one scenario are one event |

Model-derived changes (state, prediction, risk band) are recorded only once
the new value has held for 3 hours, or when it is the newest hour — this
keeps a flickering classifier from flooding the list. Seeded patients have
about 24 events for ~70 hours of data. Each event has `hour`, `type`,
`title`, `detail`, `severity`, `value`, `source` and a `simulated` flag.
`?types=alert,lab` filters; an unknown type is a 400.

## C. Scenario Simulation

`POST /api/sim/{id}/tick` with `{"scenario": "stable" | "improving" |
"deteriorating" | "continue", "hours": 1–24}` (the previous body,
`{"scenario": …}`, still works and advances one hour). Requires
`simulation.run`. `GET /api/sim/scenarios` lists the scenarios.

**What "Advance 1 Hour" does** (all in the backend, in this order):

1. The simulator's latent severity is taken from the last simulated hour, or
   — on the first simulated hour — estimated from the patient's last 3 hours
   of vitals and the latest measured lactate. The scenario moves it
   (deteriorating +0.03/h, improving −0.02/h, stable → toward 0.1, continue
   = random walk).
2. A new observation (vitals every hour; labs on their 4–8 h cadence; fluids)
   is generated from that severity and **stored** in `vitals`;
   `patients.n_hours` is incremented; a `simulation_events` row is written.
3. Features are rebuilt from the patient's full history with the training
   feature code (`ml/features.py`).
4. All 7 models predict; the predictions are stored.
5. The composite risk score is computed and stored.
6. The state engine and the alert engine run; new alerts are stored,
   including a risk-escalation alert when the score crosses into HIGH or
   CRITICAL (at most once per 6 h per level).
7. The action is written to the audit log.

The response carries the new hour, vitals, predictions, risk before/after,
engine state, new alerts and a per-hour step table. The frontend then
re-fetches risk, data quality, timeline and charts from the API — nothing is
computed or faked in React.

**Demo flow.** A low-risk patient advanced under *Deteriorating* typically
goes LOW (≈16) → MODERATE → HIGH → CRITICAL (≈80) in roughly 24–30 simulated
hours, and comes back down under *Improving*. The numbers differ on every
run because the simulator is stochastic and the models, not a script, decide.

**Fix made to the existing simulator.** The original tick re-estimated the
severity from the latest noisy observation every hour. That inversion lost
more per hour than the scenario drift added (and dropped the lactate term on
the 3 hours out of 4 without a lab), so a stable patient could never be
driven to deteriorate. Severity is now carried as simulation state in
`simulation_events`. It is never a model input.

**Safety.** The panel is labelled *Simulation mode / Synthetic scenario
simulation*; simulated hours are marked on the timeline. No treatment
suggestion is generated anywhere — a test scans every alert for order-like
wording.

## D. Data Quality Monitoring

The existing calculation (`analytics.data_quality`) is unchanged:

```text
overall = 0.4·vitals + 0.3·laboratory + 0.2·fluids + 0.1·recent vitals (6h)
          × 0.85 if any lab is older than 12 h
          × 0.5  if fewer than 6 h of data
```

where each term is the share of non-missing values. Added on top, without
altering that score:

- **Level** — `GOOD ≥ 72`, `FAIR 60–71`, `POOR < 60`. The bands sit against
  the realistic ceiling: labs are sampled every 4–8 h, so laboratory
  *completeness* is ≈ 20 % for a perfectly monitored patient and the overall
  score tops out in the mid-70s.
- **Lab timeliness** — share of the five labs measured within the last 12 h;
  the meaningful freshness indicator for intermittently sampled values.
- **Last measurement per lab**, **fields missing in the latest observation**,
  **missing-observation counts**, **hours of data**.
- **Warnings**, each derived from the record: stale lab ("Creatinine has not
  been measured recently — last measurement 14 hours ago"), never-measured
  lab, missing fields in the latest observation, recent vital-sign gaps,
  fewer than 6 h of history. A missing antibiotic record is an informational
  note, not a warning.

Shown on the patient page next to the risk score, on the simulation page,
and unit-wide on the Data Quality page (levels, warnings, oldest lab).

## E. Role-Based Services

Three roles, three services, one product. Permissions are defined once in
`backend/app/services/permissions.py`; every endpoint requires exactly one.

| Feature | Admin | Clinician | Researcher |
|---|---|---|---|
| User management (create, role, deactivate, reset password) | ✓ | — | — |
| Roles & permissions matrix | ✓ | — | — |
| Audit logs | ✓ | — | — |
| System health / model status / settings | ✓ | — | — |
| Patient list and patient page | view only | ✓ | ✓ |
| Clinician monitoring dashboard | — | ✓ | — |
| Risk score, Risk Monitoring | view | ✓ | ✓ |
| Clinical timeline | view | ✓ | ✓ |
| Alerts | view | ✓ + acknowledge | view |
| Data quality | ✓ | ✓ | ✓ |
| Explainability (SHAP) | — | ✓ | ✓ |
| Scenario simulation | — | ✓ | ✓ |
| Deployed-model list (`/api/models`) | ✓ | ✓ | ✓ |
| Model Lab, Model Performance | — | — | ✓ |
| Trajectory analysis (uses simulator ground truth) | — | — | ✓ |
| Researcher dashboard | — | — | ✓ |

Role → permission map:

```text
ADMIN       users.view  users.create  users.update  roles.view  audit.view
            system.view  models.view
            patients.view  risk.view  timeline.view  alerts.view  data_quality.view

CLINICIAN   patients.view  patients.monitor  risk.view  timeline.view
            alerts.view  alerts.acknowledge  data_quality.view
            explainability.view  simulation.run  models.view

RESEARCHER  patients.view  risk.view  timeline.view  alerts.view
            data_quality.view  explainability.view  simulation.run
            models.view  models.evaluate  trajectory.view
```

**Enforcement.** Backend: `require_permission()` returns 401 without a valid
token and 403 without the permission, and logs the denial. A deactivated
user is rejected even with an unexpired token, and a role change applies on
the next request because the role is read from the database, not from the
token. Frontend: the permission list returned at login drives the sidebar
(`nav.ts`), the route guard (`App.tsx`) and individual controls (e.g. the
simulation panel and the Acknowledge button). Editing local storage only
produces 403s.

**Dashboards** (`/` renders a different page per role):

- **Clinician** — total / high-risk / critical patients, active alerts,
  alerts awaiting review, unit risk distribution, highest-risk patients,
  largest 6-hour risk changes.
- **Researcher** — patients, observations, prediction tasks, models,
  mean macro F1, per-task performance table, dataset completeness, predicted
  recovery distribution, risk distribution, generator archetypes.
- **Admin** — users by role, API / database / model-service status, record
  counts, 24-hour activity (sign-ins, failed sign-ins, denied requests),
  recent audit events.

**Audit log.** `audit_logs` records sign-in (success / failed / deactivated),
sign-out, patient access, simulation advances, alert acknowledgement, model
analysis access, user creation, role changes, user updates and denied
requests. Repeated read events are throttled to one per user/target per 10
minutes. Passwords, tokens and request bodies are never written.

## API added or changed in Review 3

| Method | Endpoint | Purpose | Permission |
|---|---|---|---|
| GET | `/api/auth/me` | Caller's role and permissions | any signed-in user |
| POST | `/api/auth/logout` | Record sign-out in the audit log | any signed-in user |
| GET | `/api/patients/{id}/risk` | Composite risk score, contributors, history | `risk.view` |
| GET | `/api/risk` | Unit risk ranking | `risk.view` |
| GET | `/api/patients/{id}/timeline` | Clinical timeline (extended) | `timeline.view` |
| GET | `/api/patients/{id}/data-quality` | Data quality (extended) | `data_quality.view` |
| GET | `/api/data-quality` | Unit data quality (extended) | `data_quality.view` |
| GET | `/api/sim/scenarios` | Available scenarios | `simulation.run` |
| POST | `/api/sim/{id}/tick` | Advance 1–24 synthetic hours (extended) | `simulation.run` |
| POST | `/api/alerts/{id}/acknowledge` | Acknowledge an alert | `alerts.acknowledge` |
| GET | `/api/dashboard/clinician` | Clinician dashboard | `patients.monitor` |
| GET | `/api/dashboard/researcher` | Researcher dashboard | `models.evaluate` |
| GET | `/api/research/trajectories` | Cohort risk trajectories by archetype | `trajectory.view` |
| GET | `/api/admin/dashboard` | Admin dashboard | `system.view` |
| GET | `/api/admin/users` | List users | `users.view` |
| POST | `/api/admin/users` | Create user | `users.create` |
| PATCH | `/api/admin/users/{id}` | Change role / active status / password | `users.update` |
| GET | `/api/admin/roles` | Role–permission matrix | `roles.view` |
| GET | `/api/admin/audit` | Audit log (filter by action, user, status) | `audit.view` |
| GET | `/api/admin/system-health` | API / DB / model-service checks | `system.view` |
| GET | `/api/admin/settings` | Effective configuration, read-only | `system.view` |

All pre-existing endpoints keep their URLs and response fields (new fields
are additive) and now require a named permission instead of "any signed-in
user".

## Tests

`backend/tests/test_review3.py` (run with `python -m pytest tests -q` from
`backend/`; `conftest.py` runs everything against a temporary copy of the
database so the demo data is not modified). It covers the risk score
(range, level mapping, contributors, missing inputs, stored = live), the
timeline (order, patient scoping, empty and unknown patients, simulation
events), the simulation (permissions, validation, state / prediction / risk /
timeline / alert updates), data quality (stale, missing, unchanged formula)
and every role against every protected service.
