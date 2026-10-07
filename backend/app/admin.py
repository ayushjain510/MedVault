"""Admin services: user management, roles, audit log, system health.

Every route requires an admin-only permission; clinicians and researchers get
403 here regardless of what the frontend shows.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .database import get_db, User, AuditLog
from .services import audit
from .services.auth import hash_password
from .services.dashboards import admin_dashboard, system_health, system_settings
from .services.permissions import require_permission, permission_matrix, permissions_for

router = APIRouter(prefix="/api/admin", tags=["admin"])

Role = Literal["admin", "clinician", "researcher"]
USERNAME = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
PASSWORD = Field(min_length=8, max_length=128)


class UserCreate(BaseModel):
    username: str = USERNAME
    password: str = PASSWORD
    role: Role


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


def _user(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role,
            "is_active": bool(u.is_active), "created_at": u.created_at,
            "permissions": permissions_for(u.role)}


def _active_admins(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db),
              user: User = Depends(require_permission("system.view"))):
    return admin_dashboard(db)


@router.get("/users")
def list_users(db: Session = Depends(get_db),
               user: User = Depends(require_permission("users.view"))):
    return {"users": [_user(u) for u in db.query(User).order_by(User.id).all()]}


@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db),
                user: User = Depends(require_permission("users.create"))):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "A user with this username already exists")
    new = User(username=body.username, password_hash=hash_password(body.password),
               role=body.role, is_active=True, created_at=audit.now_iso())
    db.add(new)
    db.commit()
    audit.log_event(db, user, "user.create", target=new.username, detail=f"role={new.role}")
    return _user(new)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_permission("users.update"))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "User not found")
    changes = []
    removes_admin = (target.role == "admin" and target.is_active
                     and ((body.role is not None and body.role != "admin")
                          or body.is_active is False))
    if removes_admin:
        if target.id == user.id:
            raise HTTPException(400, "You cannot demote or deactivate your own account")
        if _active_admins(db) <= 1:
            raise HTTPException(400, "At least one active administrator must remain")
    if body.role is not None and body.role != target.role:
        changes.append(f"role {target.role}→{body.role}")
        target.role = body.role
    if body.is_active is not None and body.is_active != bool(target.is_active):
        changes.append("reactivated" if body.is_active else "deactivated")
        target.is_active = body.is_active
    if body.password is not None:
        target.password_hash = hash_password(body.password)
        changes.append("password reset")     # the password itself is never logged
    if not changes:
        return _user(target)
    db.commit()
    action = "user.role_change" if any(c.startswith("role") for c in changes) else "user.update"
    audit.log_event(db, user, action, target=target.username, detail="; ".join(changes))
    return _user(target)


@router.get("/roles")
def roles(user: User = Depends(require_permission("roles.view"))):
    return permission_matrix()


@router.get("/audit")
def audit_log(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
              action: str | None = Query(None, max_length=64),
              username: str | None = Query(None, max_length=32),
              status: Literal["success", "denied", "failed"] | None = None,
              db: Session = Depends(get_db),
              user: User = Depends(require_permission("audit.view"))):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action.like(f"{action}%"))
    if username:
        q = q.filter(AuditLog.username == username)
    if status:
        q = q.filter(AuditLog.status == status)
    total = q.count()
    rows = q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    actions = [a for (a,) in db.query(AuditLog.action).distinct().order_by(AuditLog.action)]
    return {"total": total, "events": [audit.serialize(r) for r in rows], "actions": actions}


@router.get("/system-health")
def health(db: Session = Depends(get_db),
           user: User = Depends(require_permission("system.view"))):
    return system_health(db)


@router.get("/settings")
def settings(user: User = Depends(require_permission("system.view"))):
    return system_settings()
