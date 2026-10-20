"""首次运行初始化 + 登录认证"""
import secrets

import pydantic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..app_settings import admin_exists, get_setting, set_setting
from ..auth import create_jwt, get_current_user, hash_password, verify_password
from ..database import get_db

router = APIRouter()


class SetupBody(pydantic.BaseModel):
    username: str
    password: str


class LoginBody(pydantic.BaseModel):
    username: str
    password: str


@router.get("/api/setup/status")
def setup_status(db: Session = Depends(get_db)):
    return {"need_setup": not admin_exists(db)}


@router.post("/api/setup/admin")
def setup_admin(body: SetupBody, db: Session = Depends(get_db)):
    """仅在没有管理员时允许初始化，防止被重置"""
    if admin_exists(db):
        raise HTTPException(status_code=403, detail="管理员已存在，禁止重复初始化")
    username = body.username.strip()
    if len(username) < 2 or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="账号至少2位，密码至少6位")
    set_setting("admin_username", username, db=db)
    set_setting("admin_password_hash", hash_password(body.password), db=db)
    # Bark 式推送密钥：初始化时自动生成
    set_setting("push_key", secrets.token_hex(8), db=db)
    token = create_jwt({"sub": username})
    return {"code": 200, "msg": "ok", "token": token}


@router.post("/api/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    if not admin_exists(db):
        raise HTTPException(status_code=403, detail="尚未初始化，请先设置管理员账号")
    if body.username.strip() != get_setting("admin_username", db=db) or not verify_password(
        body.password, get_setting("admin_password_hash", db=db)
    ):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return {"code": 200, "msg": "ok", "token": create_jwt({"sub": body.username.strip()})}


@router.get("/api/auth/me")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"code": 200, "username": user.get("sub", "")}
