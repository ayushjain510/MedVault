import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # medvault/
ML_DIR = BASE_DIR / "ml"
DATA_DIR = ML_DIR / "data"
MODELS_DIR = ML_DIR / "models"
DB_PATH = BASE_DIR / "database" / "sepsis_ai.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

DEFAULT_JWT_SECRET = "dev-only-secret-change-in-production"
JWT_SECRET = os.getenv("JWT_SECRET", DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 480

# Anyone who knows the secret can forge a valid token for any role. That is
# harmless on localhost and unacceptable on a reachable host, so warn loudly
# rather than fail (which would break the local demo flow).
JWT_SECRET_IS_DEFAULT = JWT_SECRET in (DEFAULT_JWT_SECRET, "change-me", "")
if JWT_SECRET_IS_DEFAULT:
    import warnings
    warnings.warn(
        "JWT_SECRET is unset or left at its default value. Tokens can be forged. "
        "Set a strong JWT_SECRET before exposing this service beyond localhost.",
        RuntimeWarning, stacklevel=2)

DISCLAIMER = (
    "This system is an AI-assisted research and clinical decision-support prototype. "
    "It does not diagnose disease, prescribe treatment, determine antibiotic selection, "
    "or independently recommend fluid therapy. All outputs require review by qualified "
    "healthcare professionals. All data shown is SYNTHETIC demonstration data."
)
