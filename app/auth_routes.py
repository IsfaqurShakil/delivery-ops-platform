# app/auth_routes.py
# The login endpoint.
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import User
from app.schemas import TokenOut
from app.security import DUMMY_HASH, create_access_token, verify_password

router = APIRouter(tags=["auth"])


def _invalid_login() -> HTTPException:
    # One and the same message for every kind of failure, so an attacker learns nothing.
    return HTTPException(
        status_code=401,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    username = form.username.strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        verify_password(form.password, DUMMY_HASH)  # same amount of work as a real check
        raise _invalid_login()
    if not verify_password(form.password, user.password_hash):
        raise _invalid_login()
    if not user.is_active:
        raise _invalid_login()
    return TokenOut(access_token=create_access_token(user.id, user.role.value))
