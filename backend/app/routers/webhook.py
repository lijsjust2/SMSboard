"""Webhook 接收端：接收 SmsForwarder 推送的短信/通话/心跳

两种鉴权方式：
- POST /api/webhook        ：HmacSHA256 签名（设置页配置 secret 后强制）
- POST /api/push/{push_key}：Bark 式带 Key 连接，Key 即鉴权，无需签名

请求体兼容：JSON（推荐，含消息模板）；也兼容 SmsForwarder 模板为空时的
默认表单格式 from=xx&content=xx&timestamp=xx（type 默认按 sms 处理）。
错误时返回对应 HTTP 状态码（400/403），确保 App 的「测试」能如实报错。
"""
import base64
import hashlib
import hmac
from datetime import datetime
from urllib.parse import parse_qs, unquote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import config
from ..app_settings import get_setting
from ..database import get_db
from ..models import Message
from ..services.device_state import register_heartbeat
from ..services.registry import device_display_name, ensure_device, ensure_sim
from ..ws import manager

router = APIRouter()

ALLOWED_TYPES = {"sms", "call", "heartbeat"}
DEFAULT_DEVICE_KEY = "未命名设备"


def _verify_sign(secret: str, timestamp: str, sign: str) -> bool:
    """与 SmsForwarder WebhookUtils 相同的签名算法：
    stringToSign = "$timestamp\\n" + secret
    sign = URLEncode(Base64(HmacSHA256(stringToSign, key=secret)))
    """
    try:
        sign = unquote(sign)
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
        expect = base64.b64encode(digest).decode()
        if not hmac.compare_digest(sign, expect):
            return False
        # 时间戳 ±5 分钟内有效，防重放；SmsForwarder 的 [timestamp] 为毫秒
        ts_val = int(timestamp)
        ts_sec = ts_val / 1000 if ts_val > 10_000_000_000 else ts_val
        return abs(datetime.now().timestamp() - ts_sec) <= 300
    except Exception:
        return False


async def _read_body(request: Request) -> dict:
    """JSON 优先；失败则按表单格式解析（SmsForwarder 模板为空时的默认格式）"""
    raw = await request.body()
    try:
        return await request.json()
    except Exception:
        pass
    try:
        parsed = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items() if v}
    except Exception:
        return {}


def _parse_time(raw) -> datetime:
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.isdigit()):
        # 毫秒时间戳
        return datetime.fromtimestamp(int(raw) / 1000)
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.now()


def _parse_battery(raw, plugged_raw=None, info_raw=None) -> tuple[float | None, bool, str]:
    """从心跳模板输出解析电量：battery={{BATTERY_PCT}}，plugged={{BATTERY_PLUGGED}}，info={{BATTERY_INFO}}"""
    text = f"{raw or ''} {plugged_raw or ''} {info_raw or ''}"
    pct = None
    if raw is not None and str(raw).strip():
        digits = "".join(ch for ch in str(raw) if ch.isdigit() or ch == ".")
        if digits:
            try:
                pct = float(digits)
            except ValueError:
                pct = None
    plugged = any(k in text for k in ("充电", "AC", "USB", "Wireless", "正在充电"))
    return pct, plugged, str(raw or "")


def _err(status: int, msg: str) -> JSONResponse:
    """错误必须返回真实 HTTP 状态码，否则 App「测试」会误报成功"""
    return JSONResponse(status_code=status, content={"code": status, "msg": msg})


async def _broadcast(payload: dict):
    await manager.broadcast(payload)


async def _ingest(body: dict, db: Session, push_key: str | None = None):
    """统一入库处理。push_key 非 None 表示走 Bark 式 Key 鉴权。"""
    msg_type = str(body.get("type", "")).strip().lower() or "sms"  # 表单默认格式无 type，按短信处理
    if msg_type not in ALLOWED_TYPES:
        return _err(400, f"unknown type: {msg_type}")

    timestamp = str(body.get("timestamp", ""))
    sign = str(body.get("sign", ""))

    if push_key is None:
        secret = get_setting("webhook_secret", db=db)
        if secret:
            if not _verify_sign(secret, timestamp, sign):
                return _err(403, "invalid sign")
        elif not config.ALLOW_UNSIGNED_WEBHOOK:
            return _err(403, "secret not configured")

    device_str = str(body.get("device", "")).strip() or DEFAULT_DEVICE_KEY
    sim_str = str(body.get("sim", "")).strip()
    ts = _parse_time(body.get("time") or timestamp)

    if msg_type == "heartbeat":
        pct, plugged, info = _parse_battery(body.get("battery"), body.get("plugged"), body.get("info"))
        device = ensure_device(db, device_str)
        dedup = f"hb-{device.id}-{ts.isoformat()}-{pct}-{info}"
        from ..models import Heartbeat
        if db.query(Heartbeat.id).filter(Heartbeat.dedup_key == dedup).first() is not None:
            return {"code": 200, "msg": "ok"}
        state_change = register_heartbeat(db, device.id, ts, pct, plugged, info)
        db.commit()
        name = device_display_name(device)
        await _broadcast({"event": "heartbeat", "device_id": device.id, "device_name": name,
                          "battery_pct": pct, "plugged": plugged, "battery_info": info, "online": True})
        if state_change:
            await _broadcast({"event": "device_online", "device_id": device.id,
                              "device_name": name, "battery_pct": pct})
        return {"code": 200, "msg": "ok"}

    # sms / call
    sender = str(body.get("from", "")).strip()
    content = str(body.get("content", "")).strip()
    if not sender and not content:
        return _err(400, "empty message")  # 垃圾请求体拦截
    dedup = hashlib.sha1(f"{msg_type}|{sender}|{content}|{ts.isoformat()}".encode()).hexdigest()

    if db.query(Message.id).filter(Message.dedup_key == dedup).first() is not None:
        return {"code": 200, "msg": "ok"}

    device = ensure_device(db, device_str)
    sim = ensure_sim(db, device, sim_str) if device else None
    msg = Message(
        type=msg_type, sender=sender, content=content, sim_slot=sim_str,
        device=device_str, device_id=device.id if device else None,
        sim_id=sim.id if sim else None,
        receive_time=ts, dedup_key=dedup,
    )
    db.add(msg)
    db.commit()

    await _broadcast({
        "event": "message", "type": msg_type,
        "device_id": device.id if device else None,
        "device_name": device_display_name(device),
        "sender": sender, "content": content, "sim_slot": sim_str,
        "receive_time": ts.isoformat(sep=" ", timespec="seconds"),
    })
    return {"code": 200, "msg": "ok"}


@router.post("/api/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    body = await _read_body(request)
    if not body:
        return _err(400, "bad request body")
    return await _ingest(body, db)


@router.post("/api/push/{push_key}")
async def push_by_key(push_key: str, request: Request, db: Session = Depends(get_db)):
    """Bark 式推送：URL 中的 Key 即鉴权"""
    expected = get_setting("push_key", db=db)
    if not expected or not hmac.compare_digest(push_key.strip(), expected):
        return _err(403, "invalid push key")
    body = await _read_body(request)
    if not body:
        return _err(400, "bad request body")
    return await _ingest(body, db, push_key=push_key.strip())
