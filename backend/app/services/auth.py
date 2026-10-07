from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from ..config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES
from ..database import get_db, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def create_token(username: str, role: str) -> str:
    payload = {"sub": username, "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    cred_exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                             detail="Invalid credentials",
                             headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
    except JWTError:
        raise cred_exc
    user = db.query(User).filter(User.username == username).first()
    # A deactivated account loses access immediately, even with an unexpired token.
    if user is None or user.is_active is False:
        raise cred_exc
    return user


def require_roles(*roles):
    """Legacy role check, kept for backwards compatibility. New code uses
    services.permissions.require_permission instead."""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and user.role != "admin":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker
