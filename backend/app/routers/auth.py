from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import current_user
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, UserResponse
from app.security import COOKIE_NAME, TOKEN_TTL_SECONDS, create_access_token, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


def public_user(user: User) -> dict:
    return UserResponse.model_validate(user).model_dump(mode="json")


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/api/v1",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(status_code=409, detail={"code": "AUTH_USERNAME_EXISTS", "message": "用户名已被使用"})
    now = datetime.now(UTC)
    user = User(username=username, password_hash=hash_password(payload.password), created_at=now, updated_at=now)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "AUTH_USERNAME_EXISTS", "message": "用户名已被使用"})
    db.refresh(user)
    set_session_cookie(response, create_access_token(user.id))
    return {"code": 201, "message": "success", "data": public_user(user)}


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_CREDENTIALS", "message": "用户名或密码错误"})
    set_session_cookie(response, create_access_token(user.id))
    return {"code": 200, "message": "success", "data": {"user": public_user(user), "expires_in": TOKEN_TTL_SECONDS}}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"code": 200, "message": "success", "data": public_user(user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/api/v1", httponly=True, samesite="lax")
    return {"code": 200, "message": "success", "data": {"logged_out": True}}
