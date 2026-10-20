"""应用设置存取（settings 表的内存友好封装）"""
from .database import SessionLocal
from .models import Setting

DEFAULTS = {
    "admin_username": "",
    "admin_password_hash": "",
    "webhook_secret": "",
    "push_key": "",
    "pushplus_token": "",
    "notify_on_offline": "true",
    "notify_on_online": "false",
    "heartbeat_interval_min": "5",
    "offline_multiplier": "3",
    "offline_threshold_min": "",  # 直接配置的离线阈值（分钟）；为空时 = 心跳间隔 × 倍数
}


def get_setting(key: str, db=None) -> str:
    own = db is None
    s = db or SessionLocal()
    try:
        row = s.get(Setting, key)
        return row.value if row else DEFAULTS.get(key, "")
    finally:
        if own:
            s.close()


def set_setting(key: str, value: str, db=None):
    own = db is None
    s = db or SessionLocal()
    try:
        row = s.get(Setting, key)
        if row:
            row.value = value
        else:
            row = Setting(key=key, value=value)
            s.add(row)
        s.commit()
    finally:
        if own:
            s.close()


def admin_exists(db=None) -> bool:
    return bool(get_setting("admin_password_hash", db=db))


def offline_threshold_minutes(db=None) -> int:
    """离线阈值：优先取直接配置的 offline_threshold_min，否则 = 心跳间隔 × 倍数"""
    direct = get_setting("offline_threshold_min", db=db)
    if direct and direct.strip().isdigit() and int(direct) > 0:
        return int(direct)
    interval = int(get_setting("heartbeat_interval_min", db=db) or 5)
    multiplier = int(get_setting("offline_multiplier", db=db) or 3)
    return interval * multiplier
