"""系统设置：推送 Key、webhook secret、pushplus 告警配置（仅登录后可改）"""
import secrets

import pydantic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..app_settings import get_setting, offline_threshold_minutes, set_setting
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(dependencies=[Depends(get_current_user)])


class SettingsBody(pydantic.BaseModel):
    webhook_secret: str = ""
    pushplus_token: str = ""
    notify_on_offline: bool = True
    notify_on_online: bool = False
    heartbeat_interval_min: int = 5
    offline_threshold_min: int = 15  # 离线阈值（分钟），直接可改


@router.get("/api/settings")
def read_settings(db: Session = Depends(get_db)):
    return {
        "code": 200,
        "webhook_secret": get_setting("webhook_secret", db=db),
        "push_key": get_setting("push_key", db=db),
        "pushplus_token": get_setting("pushplus_token", db=db),
        "notify_on_offline": get_setting("notify_on_offline", db=db) == "true",
        "notify_on_online": get_setting("notify_on_online", db=db) == "true",
        "heartbeat_interval_min": int(get_setting("heartbeat_interval_min", db=db) or 5),
        "offline_threshold_min": offline_threshold_minutes(db),
        "offline_threshold_minutes": offline_threshold_minutes(db),
    }


@router.post("/api/settings/push_key/regenerate")
def regenerate_push_key(db: Session = Depends(get_db)):
    """重新生成推送 Key（旧 URL 立即失效）"""
    new_key = secrets.token_hex(8)
    set_setting("push_key", new_key, db=db)
    return {"code": 200, "msg": "ok", "push_key": new_key}


@router.put("/api/settings")
def update_settings(body: SettingsBody, db: Session = Depends(get_db)):
    if not (1 <= body.heartbeat_interval_min <= 60):
        raise HTTPException(status_code=400, detail="心跳间隔需在 1~60 分钟之间")
    if not (2 <= body.offline_threshold_min <= 1440):
        raise HTTPException(status_code=400, detail="离线阈值需在 2~1440 分钟之间")
    set_setting("webhook_secret", body.webhook_secret.strip(), db=db)
    set_setting("pushplus_token", body.pushplus_token.strip(), db=db)
    set_setting("notify_on_offline", "true" if body.notify_on_offline else "false", db=db)
    set_setting("notify_on_online", "true" if body.notify_on_online else "false", db=db)
    set_setting("heartbeat_interval_min", str(body.heartbeat_interval_min), db=db)
    set_setting("offline_threshold_min", str(body.offline_threshold_min), db=db)
    return {
        "code": 200, "msg": "ok",
        "offline_threshold_minutes": offline_threshold_minutes(db),
    }
