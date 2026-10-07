"""Audit trail. Records WHO did WHAT to WHICH target — never passwords,
tokens or request bodies."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..database import AuditLog, User

THROTTLE_MINUTES = 10   # repeated read events (same user/action/target) are logged once per window


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_event(db: Session, user: User | None, action: str, target: str | None = None,
              detail: str | None = None, status: str = "success",
              username: str | None = None, throttle: bool = False) -> None:
    name = user.username if user is not None else (username or "anonymous")
    role = user.role if user is not None else None
    if throttle:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=THROTTLE_MINUTES)
                  ).isoformat(timespec="seconds")
        seen = (db.query(AuditLog.id)
                .filter(AuditLog.username == name, AuditLog.action == action,
                        AuditLog.target == target, AuditLog.timestamp >= cutoff).first())
        if seen:
            return
    db.add(AuditLog(timestamp=now_iso(), username=name, role=role, action=action,
                    target=target, detail=detail, status=status))
    db.commit()


def serialize(row: AuditLog) -> dict:
    return {"id": row.id, "timestamp": row.timestamp, "username": row.username,
            "role": row.role, "action": row.action, "target": row.target,
            "detail": row.detail, "status": row.status}
