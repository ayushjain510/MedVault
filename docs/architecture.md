# MedVault — System Architecture

```text
                ┌─────────────────────────┐
                │ Synthetic Data Simulator│  ml/data_simulator.py
                │ (240 pts, 7 archetypes) │  clearly labeled SYNTHETIC
                └───────────┬─────────────┘
                            ↓
                ┌─────────────────────────┐
                │ Validation & Missing-   │  lab sampling gaps,
                │ ness Injection          │  missing vitals
                └───────────┬─────────────┘
                            ↓
                ┌─────────────────────────┐
                │ Temporal Feature Engine │  ml/features.py
                │ 227 causal features     │  windows 3/6/12/24h
                └───────────┬─────────────┘
                            ↓
                ┌─────────────────────────┐
                │ Patient-Level Split     │  70/15/15, archetype-stratified
                └───────────┬─────────────┘
                            ↓
     ┌──────────────┬──────────────┴┬───────────────┬──────────────┐
     ↓              ↓               ↓               ↓              ↓
 RECOVERY      Antibiotic      Fluid Status   Sepsis State  Deterioration
 TRAJECTORY    Response (RF)   (LightGBM)     (XGBoost)     6/12/24h (RF)
 (RF) PRIMARY  ── treatment modules ──         context      SUPPORTING
     └──────────────┴──────┬────────┴───────────────┴──────────────┘
                           ↓
                ┌─────────────────────────┐
                │ Patient State Engine    │  services/state_engine.py
                │ RECOVERY-LED, rule-based│  STATE 0-8 + safety escalation
                │ + Treatment Response Idx│  RT 0.40 / AR 0.25 / FS 0.20 /
                └───────────┬─────────────┘  deterioration 0.15
                            ↓
      ┌─────────────────────┼──────────────────────┐
      ↓                     ↓                      ↓
┌──────────────┐  ┌───────────────────┐  ┌───────────────────┐
│ Composite    │  │ Clinical Timeline │  │ Data Quality      │
│ Risk Score   │  │ services/         │  │ services/         │
│ services/    │  │ timeline.py       │  │ analytics.py      │
│ risk.py      │  │ (aggregated on    │  │ completeness,     │
│ 0-100, 4     │  │ request)          │  │ staleness,        │
│ bands        │  │                   │  │ warnings          │
└──────┬───────┘  └─────────┬─────────┘  └─────────┬─────────┘
       └────────────────────┼──────────────────────┘
                            ↓
                ┌─────────────────────────┐
                │ Alert Engine            │  backend/app/alerts/engine.py
                │ 4 severity tiers        │  review prompts, no orders;
                │ + risk-escalation alert │  fires on band crossings
                └───────────┬─────────────┘
                            ↓
                ┌─────────────────────────┐
                │ Explainable AI Layer    │  SHAP (tree) / coef (linear)
                └───────────┬─────────────┘
                            ↓
                ┌─────────────────────────┐
                │ FastAPI Backend         │  JWT auth, bcrypt,
                │ SQLite / PostgreSQL     │  permission-based RBAC,
                │                         │  audit log
                └───────────┬─────────────┘
                            ↓
          ┌─────────────────┼─────────────────┐
          ↓                 ↓                 ↓
       ADMIN            CLINICIAN         RESEARCHER
   System Mgmt      Patient Monitoring   AI / ML Analytics
          └─────────────────┼─────────────────┘
                            ↓
                ┌─────────────────────────┐
                │ React + TS Dashboard    │  Vite, Tailwind, Recharts
                │ role-specific home,     │  one visual language,
                │ navigation and services │  three services
                └───────────┬─────────────┘
                            ↓
                ┌─────────────────────────┐
                │ Scenario Simulation     │  services/simulator.py
                │ new synthetic hour →    │  loops back into the
                │ the whole pipeline again│  feature engine above
                └─────────────────────────┘
```

Model names in the diagram are the selected models in
`ml/models/report.json` (see `model_evaluation.md`).

## Entity relationships

```text
patients 1───* vitals
patients 1───* antibiotic_records
patients 1───* predictions        (per hour × 7 tasks)
patients 1───* alerts             (acknowledged flag)
patients 1───* risk_scores        (per hour: score, level, components)
patients 1───* simulation_events  (one per simulated hour: scenario, user)
users                             (role: admin | clinician | researcher; is_active)
audit_logs                        (who / action / target / status / time)
```

`risk_scores`, `simulation_events`, `audit_logs` and `users.is_active` were
added for Review 3. `database.ensure_schema()` creates them on start-up, so a
database seeded by the previous version keeps working; risk history is
back-filled on first use.

## Key flows

**Batch (seed)**: simulator → features.parquet → 7 models predict every hour →
predictions + alerts persisted → risk score computed for every patient-hour →
dashboard reads from DB.

**Scenario simulation** (`POST /api/sim/{pid}/tick`, body
`{scenario, hours}`): for each hour — generate the next synthetic observation →
append to DB → rebuild features from the full history → run all 7 models →
persist predictions → compute and persist the risk score → state engine →
alert engine (including a risk-escalation alert) → record a simulation event.
The frontend then re-fetches risk, data quality, timeline and patient data.
Details: `review3.md`.

**Explanation** (`GET /api/explanations/{pid}?task=`): rebuild features from
stored history → local SHAP/coefficient contributions for the latest hour.

## Role-based access

Authorization is permission-based. Each endpoint declares one permission
(`Depends(require_permission("…"))`); the role → permission map lives in
`backend/app/services/permissions.py` and nowhere else. The frontend receives
the same permission list at login and uses it for navigation and route
guards, but the API is the security boundary: a request without the
permission gets **403** whatever the UI shows, and the denial is written to
the audit log.

| Endpoint group | Permission | admin | clinician | researcher |
|---|---|---|---|---|
| patients, vitals, labs, fluids, antibiotics, predictions, state, overview | `patients.view` | ✓ (read-only) | ✓ | ✓ |
| `/api/patients/{id}/risk`, `/api/risk` | `risk.view` | ✓ | ✓ | ✓ |
| `/api/patients/{id}/timeline` | `timeline.view` | ✓ | ✓ | ✓ |
| `/api/alerts` | `alerts.view` | ✓ | ✓ | ✓ |
| `/api/alerts/{id}/acknowledge` | `alerts.acknowledge` | ✗ | ✓ | ✗ |
| `/api/data-quality`, `/api/patients/{id}/data-quality` | `data_quality.view` | ✓ | ✓ | ✓ |
| `/api/explanations/{id}` | `explainability.view` | ✗ | ✓ | ✓ |
| `/api/sim/*` | `simulation.run` | ✗ | ✓ | ✓ |
| `/api/models` | `models.view` | ✓ | ✓ | ✓ |
| `/api/model-performance`, `/api/dashboard/researcher` | `models.evaluate` | ✗ | ✗ | ✓ |
| `/api/research/trajectories` | `trajectory.view` | ✗ | ✗ | ✓ |
| `/api/dashboard/clinician` | `patients.monitor` | ✗ | ✓ | ✗ |
| `/api/admin/users` (GET / POST / PATCH) | `users.view` / `users.create` / `users.update` | ✓ | ✗ | ✗ |
| `/api/admin/roles` | `roles.view` | ✓ | ✗ | ✗ |
| `/api/admin/audit` | `audit.view` | ✓ | ✗ | ✗ |
| `/api/admin/dashboard`, `/system-health`, `/settings` | `system.view` | ✓ | ✗ | ✗ |

Change from the previous version: `admin` used to pass every role check
implicitly. It is now a role like the others — system management plus
read-only oversight of patient data — and no longer has access to the Model
Lab, SHAP explanations or the simulation.
