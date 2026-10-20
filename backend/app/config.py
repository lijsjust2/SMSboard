import os
import secrets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.environ.get("SMSBOARD_DB", os.path.join(DATA_DIR, "smsboard.db"))
FRONTEND_DIST = os.environ.get(
    "SMSBOARD_FRONTEND_DIST", os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
)

PORT = int(os.environ.get("SMSBOARD_PORT", "9990"))

# JWT 签名密钥：未提供时自动生成并持久化，重启不失效
_jwt_secret_file = os.path.join(DATA_DIR, ".jwt_secret")


def _load_jwt_secret() -> str:
    env = os.environ.get("SMSBOARD_JWT_SECRET")
    if env:
        return env
    if os.path.exists(_jwt_secret_file):
        with open(_jwt_secret_file, "r", encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                return s
    s = secrets.token_hex(32)
    with open(_jwt_secret_file, "w", encoding="utf-8") as f:
        f.write(s)
    return s


JWT_SECRET = _load_jwt_secret()
JWT_EXPIRE_HOURS = int(os.environ.get("SMSBOARD_JWT_EXPIRE_HOURS", "168"))  # 7 天

# 心跳间隔（分钟）：与手机端定时任务保持一致，决定离线判定灵敏度
HEARTBEAT_INTERVAL_MIN = int(os.environ.get("SMSBOARD_HEARTBEAT_INTERVAL_MIN", "5"))
# 离线阈值 = 心跳间隔 × 倍数（默认 3 倍，容忍弱网重试）
OFFLINE_MULTIPLIER = int(os.environ.get("SMSBOARD_OFFLINE_MULTIPLIER", "3"))

# 未配置 secret 时是否接受未签名 webhook（局域网自用可开）
ALLOW_UNSIGNED_WEBHOOK = os.environ.get("SMSBOARD_ALLOW_UNSIGNED", "true").lower() == "true"

PUSHPLUS_API = "https://www.pushplus.plus/send"
