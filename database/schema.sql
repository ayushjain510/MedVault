-- MedVault database schema (PostgreSQL dialect; SQLite is used automatically
-- for local development via SQLAlchemy).

CREATE TABLE patients (
    patient_id  VARCHAR PRIMARY KEY,
    age         INTEGER,
    sex         CHAR(1),
    archetype   VARCHAR,     -- simulator ground truth (researcher use only)
    n_hours     INTEGER,
    admission_offset_hours INTEGER,
    icu         BOOLEAN DEFAULT TRUE
);

CREATE TABLE vitals (
    id          SERIAL PRIMARY KEY,
    patient_id  VARCHAR REFERENCES patients(patient_id),
    hour        INTEGER,
    heart_rate  REAL, sbp REAL, dbp REAL, map REAL,
    resp_rate   REAL, spo2 REAL, temperature REAL,
    lactate     REAL, wbc REAL, creatinine REAL, bilirubin REAL, platelets REAL,
    urine_output REAL, fluid_input REAL, fluid_output REAL
);
CREATE INDEX ix_vitals_pid_hour ON vitals(patient_id, hour);

CREATE TABLE antibiotic_records (
    id             SERIAL PRIMARY KEY,
    patient_id     VARCHAR REFERENCES patients(patient_id),
    start_hour     INTEGER,
    abx_class      VARCHAR,
    duration_hours INTEGER,
    culture_taken  BOOLEAN,
    culture_positive BOOLEAN,
    organism       VARCHAR,
    susceptible    BOOLEAN
);
CREATE INDEX ix_abx_pid ON antibiotic_records(patient_id);

CREATE TABLE predictions (
    id              SERIAL PRIMARY KEY,
    patient_id      VARCHAR REFERENCES patients(patient_id),
    hour            INTEGER,
    task            VARCHAR,          -- sepsis_state | deterioration_6h | antibiotic_response | fluid_status | recovery
    predicted_class INTEGER,
    predicted_label VARCHAR,
    probability     REAL,
    probabilities_json TEXT
);
CREATE INDEX ix_pred_pid_hour_task ON predictions(patient_id, hour, task);

CREATE TABLE alerts (
    id          SERIAL PRIMARY KEY,
    patient_id  VARCHAR REFERENCES patients(patient_id),
    hour        INTEGER,
    severity    VARCHAR,              -- critical | high | moderate | info
    category    VARCHAR,
    title       VARCHAR,
    message     TEXT,
    variable    VARCHAR,
    confidence  REAL,
    acknowledged BOOLEAN DEFAULT FALSE
);
CREATE INDEX ix_alerts_pid ON alerts(patient_id);

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR UNIQUE,
    password_hash VARCHAR,             -- bcrypt
    role          VARCHAR,             -- admin | clinician | researcher
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,   -- deactivated users cannot sign in
    created_at    VARCHAR              -- ISO-8601 UTC
);

-- ---- Review 3 ---------------------------------------------------------

-- MedVault Composite Risk Score per patient-hour (backend/app/services/risk.py)
CREATE TABLE risk_scores (
    id              SERIAL PRIMARY KEY,
    patient_id      VARCHAR REFERENCES patients(patient_id),
    hour            INTEGER,
    score           INTEGER,           -- 0-100, NULL = insufficient data
    level           VARCHAR,           -- LOW | MODERATE | HIGH | CRITICAL | INSUFFICIENT DATA
    components_json TEXT               -- contributors and their points
);
CREATE INDEX ix_risk_pid_hour ON risk_scores(patient_id, hour);

-- One row per simulated hour (scenario simulation)
CREATE TABLE simulation_events (
    id          SERIAL PRIMARY KEY,
    patient_id  VARCHAR REFERENCES patients(patient_id),
    hour        INTEGER,
    scenario    VARCHAR,               -- stable | improving | deteriorating | continue
    severity    REAL,                  -- simulator state; never a model input
    username    VARCHAR,
    created_at  VARCHAR
);
CREATE INDEX ix_sim_pid ON simulation_events(patient_id);

-- Audit trail: never stores passwords, tokens or request bodies
CREATE TABLE audit_logs (
    id         SERIAL PRIMARY KEY,
    timestamp  VARCHAR,                -- ISO-8601 UTC
    username   VARCHAR,
    role       VARCHAR,
    action     VARCHAR,                -- auth.login | patient.view | simulation.advance | user.create | ...
    target     VARCHAR,
    detail     TEXT,
    status     VARCHAR                 -- success | denied | failed
);
CREATE INDEX ix_audit_ts ON audit_logs(timestamp);
