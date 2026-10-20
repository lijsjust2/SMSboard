"""Webhook 验签与入库测试：签名算法必须与 SmsForwarder WebhookUtils 一致"""
import base64
import hashlib
import hmac
import time
from urllib.parse import quote

from app.app_settings import set_setting


def make_sign(secret: str, timestamp: str) -> str:
    """复刻 SmsForwarder 的签名：URLEncode(Base64(HmacSHA256("$ts\n"+secret, key=secret)))"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    return quote(base64.b64encode(digest).decode())


def test_unsigned_accepted_when_no_secret(client):
    r = client.post("/api/webhook", json={
        "type": "sms", "from": "10086", "content": "测试短信",
        "sim": "SIM1_13800000000", "device": "OPPO",
        "time": "2026-10-20 12:00:00", "timestamp": int(time.time() * 1000),
    })
    assert r.json() == {"code": 200, "msg": "ok"}


def test_signed_sms_ingest_and_dedup(client, db):
    set_setting("webhook_secret", "my-secret", db=db)
    ts = str(int(time.time() * 1000))
    body = {
        "type": "sms", "from": "10688514111669", "content": "验证码 421271",
        "sim": "SIM2_15013303441", "device": "OPPO",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"), "timestamp": ts,
        "sign": make_sign("my-secret", ts),
    }
    r1 = client.post("/api/webhook", json=body)
    r2 = client.post("/api/webhook", json=body)  # 重放同一条 → 去重
    assert r1.json()["code"] == 200 and r2.json()["code"] == 200

    r = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert r.status_code == 403  # 管理员未初始化时禁止登录


def test_invalid_sign_rejected(client, db):
    set_setting("webhook_secret", "my-secret", db=db)
    ts = str(int(time.time() * 1000))
    r = client.post("/api/webhook", json={
        "type": "sms", "from": "10086", "content": "x",
        "timestamp": ts, "sign": make_sign("wrong-secret", ts),
    })
    assert r.json()["code"] == 403


def test_stale_timestamp_rejected(client, db):
    set_setting("webhook_secret", "my-secret", db=db)
    old_ts = str(int((time.time() - 600) * 1000))
    r = client.post("/api/webhook", json={
        "type": "sms", "from": "10086", "content": "x",
        "timestamp": old_ts, "sign": make_sign("my-secret", old_ts),
    })
    assert r.json()["code"] == 403


def test_heartbeat_battery_parsed(client, db):
    ts = str(int(time.time() * 1000))
    r = client.post("/api/webhook", json={
        "type": "heartbeat", "battery": "85%", "info": "85% - 充电中",
        "device": "OPPO", "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": ts,
    })
    assert r.json()["code"] == 200

    setup = client.post("/api/setup/admin", json={"username": "admin", "password": "secret123"})
    assert setup.status_code == 200
    headers = {"Authorization": f"Bearer {setup.json()['token']}"}
    summary = client.get("/api/stats/summary", headers=headers).json()
    assert summary["battery_pct"] == 85.0
    assert summary["plugged"] is True
    assert summary["online_now"] is True

    # 重复初始化应被拒绝
    assert client.post("/api/setup/admin", json={"username": "a", "password": "b"}).status_code == 403
