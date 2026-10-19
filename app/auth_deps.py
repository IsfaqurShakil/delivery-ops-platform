# app/auth_deps.py
# FastAPI "dependencies" that protect endpoints: who is logged in, and does their role allow this?
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import User, UserRole
from app.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")  # tells the /docs page where to log in


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        claims = decode_token(token)  # checks signature and expiry
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized()
    user = db.get(User, user_id)  # we always re-read the user from the database
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def require_roles(*allowed: UserRole):
    # Builds a dependency that lets only the listed roles through.
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="You do not have permission to do this")
        return user

    return checker
