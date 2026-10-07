"""Centralized role -> permission mapping for MedVault.

Every protected endpoint declares the ONE permission it needs via
`Depends(require_permission("..."))`; which roles hold that permission is
decided here and nowhere else. The frontend receives the same list at login
(and from /api/auth/me) to shape navigation, but that is presentation only —
this module, enforced in the API, is the security boundary.

The three roles are different services, not different privilege levels:

  admin       platform management (users, roles, audit, system health)
  clinician   patient monitoring (risk, alerts, timeline, simulation)
  researcher  AI / ML analytics (model lab, performance, trajectories)

Admin is deliberately NOT a superuser: it gets read-only oversight of patient
data but cannot run simulations, acknowledge alerts or open the Model Lab.
"""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import User, get_db
from . import audit
from .auth import get_current_user

ROLES = ("admin", "clinician", "researcher")

PERMISSIONS: dict[str, str] = {
    "patients.view": "View the patient list, patient details, vitals, labs, fluids and antibiotics",
    "patients.monitor": "Clinician monitoring dashboard (unit-level patient prioritisation)",
    "risk.view": "View the MedVault Composite Risk Score and its contributors",
    "timeline.view": "View the clinical timeline of a patient",
    "alerts.view": "View alerts",
    "alerts.acknowledge": "Acknowledge an alert after review",
    "data_quality.view": "View data-quality monitoring",
    "explainability.view": "View local SHAP explanations of model predictions",
    "simulation.run": "Advance a patient through the synthetic scenario simulation",
    "models.view": "View which model is deployed for each prediction task",
    "models.evaluate": "Model Lab: full evaluation metrics, model comparison, global importance",
    "trajectory.view": "Cohort-level trajectory analysis (includes simulator ground truth)",
    "users.view": "List user accounts",
    "users.create": "Create user accounts",
    "users.update": "Change a user's role, password or active status",
    "roles.view": "View the role and permission matrix",
    "audit.view": "View the audit log",
    "system.view": "View system health, model-service status and configuration",
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset({
        "users.view", "users.create", "users.update", "roles.view", "audit.view",
        "system.view", "models.view",
        # read-only oversight of the data the platform holds
        "patients.view", "risk.view", "timeline.view", "alerts.view", "data_quality.view",
    }),
    "clinician": frozenset({
        "patients.view", "patients.monitor", "risk.view", "timeline.view",
        "alerts.view", "alerts.acknowledge", "data_quality.view",
        "explainability.view", "simulation.run", "models.view",
    }),
    "researcher": frozenset({
        "patients.view", "risk.view", "timeline.view", "alerts.view",
        "data_quality.view", "explainability.view", "simulation.run",
        "models.view", "models.evaluate", "trajectory.view",
    }),
}

ROLE_DESCRIPTIONS = {
    "admin": "System management — users, roles, audit trail, platform health.",
    "clinician": "Patient monitoring — risk, alerts, clinical timeline, simulation.",
    "researcher": "AI / ML analytics — model lab, performance, trajectory analysis.",
}

assert all(p in PERMISSIONS for perms in ROLE_PERMISSIONS.values() for p in perms)


def permissions_for(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(permission: str):
    """FastAPI dependency: 401 without a valid token, 403 without the permission."""
    if permission not in PERMISSIONS:
        raise KeyError(f"unknown permission {permission!r}")

    def checker(request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> User:
        if not has_permission(user.role, permission):
            audit.log_event(db, user, "access.denied", target=request.url.path,
                            detail=f"missing permission {permission}", status="denied",
                            throttle=True)
            raise HTTPException(status_code=403,
                                detail=f"Insufficient permissions: '{permission}' is required")
        return user
    return checker


def permission_matrix() -> dict:
    return {
        "roles": [{"role": r, "description": ROLE_DESCRIPTIONS[r],
                   "permissions": permissions_for(r)} for r in ROLES],
        "permissions": [{"key": k, "description": v,
                         **{r: has_permission(r, k) for r in ROLES}}
                        for k, v in PERMISSIONS.items()],
    }
