from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import ChangePasswordIn, LoginIn, TokenOut
from app.api.deps import get_current_user


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(User).filter(User.username == payload.username, User.is_active == True).first()  # noqa: E712
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid username or password")
    return TokenOut(access_token=create_access_token(user.username))


@router.post("/me/password")
def change_password(
    payload: ChangePasswordIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    user = db.get(User, current_user.id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="user not found")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="current password is incorrect")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="new password must be different")
    user.password_hash = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    return {"ok": True}
