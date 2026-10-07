"""Run the test suite against a throw-away COPY of the seeded database.

Several tests write (simulation ticks, user management, alert acknowledgement).
Pointing DATABASE_URL at a temp copy before the app is imported keeps the
demo database exactly as seeded, however often the tests run.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SOURCE_DB = BASE / "database" / "sepsis_ai.db"

if not SOURCE_DB.exists():
    raise RuntimeError(f"{SOURCE_DB} not found - run `python seed.py` from backend/ first")

_tmp = Path(tempfile.mkdtemp(prefix="medvault-tests-")) / "test.db"
shutil.copy(SOURCE_DB, _tmp)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"

sys.path.insert(0, str(BASE / "backend"))
sys.path.insert(0, str(BASE / "ml"))
