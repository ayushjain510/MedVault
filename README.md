# MedVault

**AI-Based Antibiotic Response, Fluid Status & Recovery Trajectory Monitoring System**
*Antibiotic Response • Fluid Status • Recovery Intelligence*

> ⚠️ **AI-generated clinical decision support. This system does not diagnose
> disease or independently prescribe antibiotics or fluid therapy. All outputs
> require review by qualified healthcare professionals. All included data is
> SYNTHETIC demonstration data.**

## Overview

A research-grade clinical AI platform that answers a recovery-centric
question — *is this patient recovering, and is treatment working?* — rather
than generic deterioration prediction. Seven trained model tasks (recovery
trajectory RT-0..5, antibiotic response AR-0..4, fluid status FS-0..5, an
8-state sepsis classifier, and 6/12/24h deterioration horizons) run over
strictly-causal temporal features and are combined by a documented
**recovery-led rule-based Patient State Engine** (STATE 0–8) kept explicitly
separate from the ML predictions.

**Recovery trajectory is the primary output.** It leads the patient page (with
a longitudinal 0–100 recovery score), leads the unit table, and is the top
priority in the state engine and the highest-weighted term (0.40) in the
Treatment Response Index. The deterioration models are retained as a
**supporting signal** — collapsed in the UI, corroborating rather than
classifying — with one deliberate exception: a ≥85% 6h deterioration
probability still escalates on its own, so the reframing can never present a
very high short-term risk as an improving patient.

## Review 3 — one connected platform

MedVault is now an AI-assisted ICU monitoring and decision-support platform
rather than a model demo. Five additions sit on top of the existing pipeline
and feed each other (details: [docs/review3.md](docs/review3.md)):

- **Patient Risk Score** — a transparent 0–100 *MedVault Composite Risk
  Score* (LOW / MODERATE / HIGH / CRITICAL) built from the existing model
  outputs, with every contributor and its points shown. Research indicator,
  not a validated clinical score.
- **Clinical Timeline** — one chronological list per patient: treatment,
  threshold crossings in vitals, lab step changes, fluid milestones, state
  and risk-level changes, alerts and simulated hours.
- **Scenario Simulation** — choose *Stable / Improving / Deteriorating*,
  advance 1 or 6 hours, and the real pipeline re-runs: new observation →
  features → 7 models → risk score → state engine → alerts → timeline.
- **Data Quality Monitoring** — completeness, lab freshness and concrete
  warnings next to the risk score they qualify.
- **Role-based services** — Admin (system management), Clinician (patient
  monitoring) and Researcher (AI / ML analytics) each get their own
  dashboard, navigation and actions, enforced in the API by a central
  permission map (403 for anything outside the role) and recorded in an
  audit log.

```text
Secure access → patient data → ML predictions → explainability →
risk assessment → timeline → alerts → simulation → updated predictions
```

## Key features

- **Recovery trajectory as the headline output**: RT-0..5 predicted **12 hours
  ahead**, plus a model-derived 0–100 recovery score charted over the whole stay
- **Independent labels**: each task derived from a disjoint observable subsystem
  (organ dysfunction / infection markers / fluid-renal), not from one shared
  latent variable — verified by mutual information, reported in the docs
- **Multi-task temporal ML**: 227 causal features (3/6/12/24h windows,
  slopes, variability, fluid balance, missingness indicators); 4-model
  comparison per task (LogReg / RF / XGBoost / LightGBM)
- **Recovery-led Patient State Engine + Treatment Response Index**
  (research-derived composite, labeled as such)
- **Insufficient-data handling**: <6h of observations → "Insufficient Data",
  never a forced prediction
- **Explainable AI**: global + local SHAP with non-causality caveats
- **"What changed?" panel**: 6h-vs-previous-6h deltas with favourability
- **Exploratory trajectory similarity**: z-scored nearest-neighbour search
  over 24h trend fingerprints
- **Data Quality page**: per-patient completeness, staleness, and a
  confidence modifier that degrades with poor data
- **Alert engine** (critical/high/moderate/info) — review prompts, never
  orders (test-enforced)
- **Scenario simulation** through the full real pipeline (labeled
  SIMULATION MODE), microbiology/culture timeline, JWT auth + permission-based
  RBAC with an audit log, model versioning (`ANT-RAN-2.0`-style), error
  analysis, calibration curves

## Dataset

Target dataset: **MIMIC-IV** (hospital + ICU modules). It is
credentialed-access — PhysioNet account, CITI training, and a signed DUA are
required; the MIMIC-IV *demo* dataset is available for schema exploration.
This repository ships a clearly-labeled **synthetic generator** (240 patients,
7 trajectory archetypes, latent-severity physiology, realistic lab sampling
gaps) so everything runs out of the box; swapping in MIMIC-IV means replacing
only the loader — features, labels, training and serving are unchanged.

## Model results (validation, selected models)

| Task | Selected | Macro F1 | Macro recall |
|---|---|---|---|
| **Recovery trajectory (RT)** — primary, 12h ahead | Random Forest | 0.637 | 0.682 |
| Antibiotic response (AR) — 12h ahead | Random Forest | 0.836 | 0.850 |
| Fluid status (FS) — current state | LightGBM | 0.968 | 0.974 |
| Sepsis state (8-class) | XGBoost | 0.778 | 0.779 |
| Deterioration 6h — supporting | Random Forest | 0.807 | 0.834 |
| Deterioration 12h — supporting | Random Forest | 0.843 | 0.871 |
| Deterioration 24h — supporting | Random Forest | 0.872 | 0.888 |

Recovery — the primary task — is deliberately the *hardest*: it forecasts the
organ-dysfunction trajectory **12 hours ahead** from past data only, rather
than describing the current one. Its macro F1 fell from 0.765 to 0.637 once
the labels were made independent and forward-looking and right-censored rows
were dropped. That drop is the honest cost of turning label *recomputation*
into genuine *prediction* — the earlier, higher number measured an easier
problem. Fluid status stays high because cumulative balance is measured
arithmetic, not a forecast.

All metrics come from actual experiments on the synthetic held-out data and
**will not transfer to real ICU data** (`docs/limitations.md`). Full tables,
calibration and confusion matrices: `docs/model_evaluation.md`,
`ml/models/report.json`, and the in-app Model Lab.

## Quick start

```bash
# 1. ML pipeline (from medvault/ml) — the dataset CSVs are included, so
#    data_simulator.py is only needed to regenerate them
python features.py && python train.py && python explain.py

# 2. Database + backend (from medvault/backend)
pip install -r requirements.txt
python seed.py
python -m uvicorn app.main:app --port 8000

# 3. Frontend (from medvault/frontend)
npm install && npm run dev     # http://localhost:5173
```

Demo accounts — each opens a different service:

| Account | Service | Home page |
|---|---|---|
| `clinician` / `clin123` | Patient monitoring | Clinician Dashboard |
| `researcher` / `res123` | AI / ML analytics | Researcher Dashboard |
| `admin` / `admin123` | System management | Admin Dashboard |

Tests: `cd backend && python -m pytest tests -q` (174 tests; they run against
a temporary copy of the database, so the seeded demo data is left untouched).
API docs: `http://localhost:8000/docs`

`python seed.py` rebuilds the database from scratch — stop the backend first
(on Windows the running server keeps the SQLite file open), and use it to
reset a demo after simulating.

## Sharing & deployment

### Docker (one command, works anywhere)

```bash
JWT_SECRET=$(openssl rand -hex 32) docker compose up --build
```

Frontend on `:8080`, API on `:8000`. The backend **seeds its own database on
first boot** from the trained models (`backend/entrypoint.sh`), so a fresh
clone works with no manual seeding; the `./database` volume keeps it across
restarts.

### Show someone on your network

Run the dev servers bound to all interfaces, then share `http://<your-ip>:5173`:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
npm run dev -- --host
```

Find your IP with `ipconfig` (Windows). Same network only, nothing exposed to
the internet, and it stops when your machine does.

### Public deployment (persistent link)

`render.yaml` is a ready Render blueprint — push the repo to GitHub, then
**New → Blueprint** in Render and point it at the repo. It provisions the API
(Docker, with a 1 GB disk for the database) and the frontend (static build),
generates a strong `JWT_SECRET`, and wires the two together via
`ALLOWED_ORIGINS` / `VITE_API_BASE`. You'll need to sign in to Render yourself —
account creation and billing aren't something this repo can do for you.

Any other host works the same way; the only two settings that matter when the
frontend and API live on different domains are:

| Variable | Where | Purpose |
|---|---|---|
| `JWT_SECRET` | backend | **Required.** Tokens are forgeable without it; the app logs a warning if left at the default. |
| `ALLOWED_ORIGINS` | backend | Comma-separated frontend origins for CORS. |
| `VITE_API_BASE` | frontend build | API origin, e.g. `https://medvault-api.onrender.com`. Omit when same-origin. |

> Deploying makes the demo publicly reachable. The data is synthetic, but the
> disclaimer and "research prototype" framing must stay visible — this is not a
> clinical tool.

## Documentation

| Doc | Contents |
|---|---|
| [review3.md](docs/review3.md) | **Review 3**: risk score, clinical timeline, scenario simulation, data quality, role-based services, new APIs |
| [architecture.md](docs/architecture.md) | system/data-flow diagrams, ER model, permission matrix |
| [methodology.md](docs/methodology.md) | features, leakage prevention, model selection |
| [label_definitions.md](docs/label_definitions.md) | exact AR/FS/RT/STATE rules, windows, cohort |
| [model_evaluation.md](docs/model_evaluation.md) | full metric tables, calibration |
| [error_analysis.md](docs/error_analysis.md) | FP/FN clusters, confusions, uncertainty |
| [ethics.md](docs/ethics.md) | privacy, bias, automation bias, dataset shift |
| [limitations.md](docs/limitations.md) | honest limitations |

## Structure

```
medvault/
├── ml/          simulator, features, labels, training (4 models × 7 tasks), SHAP
├── backend/     FastAPI: API, auth, permissions, risk score, timeline, simulator,
│                state engine, analytics, alerts, dashboards, admin, audit, seed, tests
├── frontend/    React+TS: role dashboards, Patients, Patient page, Risk Monitoring,
│                Clinical Timeline, Scenario Simulation, Alerts, Explainability,
│                Model Lab, Model Performance, Trajectory Analysis, Data Quality, Admin
├── database/    schema.sql, SQLite dev DB
└── docs/        8 documents above
```

## Future work

MIMIC-IV adapter, probability recalibration, SOFA/qSOFA side-by-side,
transformer temporal models at larger scale, drift monitoring, alarm-burden
tuning, subgroup fairness reporting, external + prospective validation,
causal treatment-response modeling.
