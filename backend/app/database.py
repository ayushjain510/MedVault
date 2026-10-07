from sqlalchemy import (create_engine, Column, Integer, Float, String, Boolean,
                        Text, ForeignKey, Index, inspect, text)
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}
                       if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


class Patient(Base):
    __tablename__ = "patients"
    patient_id = Column(String, primary_key=True)
    age = Column(Integer)
    sex = Column(String(1))
    archetype = Column(String)          # simulator ground truth, researcher-only
    n_hours = Column(Integer)
    admission_offset_hours = Column(Integer)
    icu = Column(Boolean, default=True)


class Vital(Base):
    __tablename__ = "vitals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.patient_id"), index=True)
    hour = Column(Integer)
    heart_rate = Column(Float)
    sbp = Column(Float)
    dbp = Column(Float)
    map = Column(Float)
    resp_rate = Column(Float)
    spo2 = Column(Float)
    temperature = Column(Float)
    lactate = Column(Float)
    wbc = Column(Float)
    creatinine = Column(Float)
    bilirubin = Column(Float)
    platelets = Column(Float)
    urine_output = Column(Float)
    fluid_input = Column(Float)
    fluid_output = Column(Float)
    __table_args__ = (Index("ix_vitals_pid_hour", "patient_id", "hour"),)


class AntibioticRecord(Base):
    __tablename__ = "antibiotic_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.patient_id"), index=True)
    start_hour = Column(Integer)
    abx_class = Column(String)
    duration_hours = Column(Integer)
    culture_taken = Column(Boolean)
    culture_positive = Column(Boolean)
    organism = Column(String, nullable=True)
    susceptible = Column(Boolean)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.patient_id"), index=True)
    hour = Column(Integer)
    task = Column(String)               # sepsis_state | deterioration_6h | ...
    predicted_class = Column(Integer)
    predicted_label = Column(String)
    probability = Column(Float)
    probabilities_json = Column(Text)
    __table_args__ = (Index("ix_pred_pid_hour_task", "patient_id", "hour", "task"),)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.patient_id"), index=True)
    hour = Column(Integer)
    severity = Column(String)           # critical | high | moderate | info
    category = Column(String)
    title = Column(String)
    message = Column(Text)
    variable = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    acknowledged = Column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String)               # admin | clinician | researcher
    is_active = Column(Boolean, default=True, nullable=False, server_default="1")
    created_at = Column(String, nullable=True)   # ISO-8601 UTC


class RiskScore(Base):
    """MedVault Composite Risk Score per patient-hour (services/risk.py).

    Persisted so the unit views and the clinical timeline can read risk history
    without recomputing it; always written by the same function that serves
    GET /api/patients/{id}/risk."""
    __tablename__ = "risk_scores"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.patient_id"), index=True)
    hour = Column(Integer)
    score = Column(Integer, nullable=True)      # None = insufficient data
    level = Column(String)                      # LOW | MODERATE | HIGH | CRITICAL | INSUFFICIENT DATA
    components_json = Column(Text)
    __table_args__ = (Index("ix_risk_pid_hour", "patient_id", "hour"),)


class SimulationEvent(Base):
    """One row per simulated hour, so synthetic hours stay distinguishable
    from the seeded record on the clinical timeline."""
    __tablename__ = "simulation_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.patient_id"), index=True)
    hour = Column(Integer)
    scenario = Column(String)
    severity = Column(Float)        # simulator's latent state after this hour; never a model input
    username = Column(String)
    created_at = Column(String)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, index=True)      # ISO-8601 UTC
    username = Column(String, index=True)
    role = Column(String)
    action = Column(String, index=True)         # e.g. auth.login, simulation.advance
    target = Column(String, nullable=True)      # patient id, username, ...
    detail = Column(Text, nullable=True)        # never passwords or tokens
    status = Column(String, default="success")  # success | denied | failed


def ensure_schema():
    """Create tables added after the first release and add new columns to an
    existing database, so a database seeded by an older version keeps working."""
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        if "is_active" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        if "created_at" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN created_at VARCHAR"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
