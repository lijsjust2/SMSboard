"""Bark 式带 Key 推送测试"""
import time

import pytest


@pytest.fixture()
def auth(client):
    r = client.post("/api/setup/admin", json={"username": "admin", "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_push_key_generated_on_setup(client, auth):
    s = client.get("/api/settings", headers=auth).json()
    assert s["push_key"], "初始化后应自动生成 push_key"
    assert len(s["push_key"]) == 16


def test_push_with_key_no_sign_needed(client, auth):
    s = client.get("/api/settings", headers=auth).json()
    key = s["push_key"]
    ts = str(int(time.time() * 1000))
    # 正确 key，无签名 → 接受
    r = client.post(f"/api/push/{key}", json={
        "type": "sms", "from": "10086", "content": "key鉴权短信", "device": "OPPO",
        "sim": "SIM1_13800000000", "timestamp": ts,
    })
    assert r.json()["code"] == 200

    # 错误 key → 拒绝
    bad = client.post("/api/push/0000000000000000", json={
        "type": "sms", "from": "10086", "content": "x", "timestamp": ts,
    })
    assert bad.json()["code"] == 403


def test_regenerate_push_key(client, auth):
    old = client.get("/api/settings", headers=auth).json()["push_key"]
    new = client.post("/api/settings/push_key/regenerate", headers=auth).json()["push_key"]
    assert new != old
    ts = str(int(time.time() * 1000))
    assert client.post(f"/api/push/{old}", json={
        "type": "sms", "from": "1", "content": "x", "timestamp": ts,
    }).json()["code"] == 403, "旧 Key 应失效"
    assert client.post(f"/api/push/{new}", json={
        "type": "sms", "from": "1", "content": "x", "timestamp": ts,
    }).json()["code"] == 200


def test_key_auth_works_alongside_device_registration(client, auth):
    s = client.get("/api/settings", headers=auth).json()
    key = s["push_key"]
    ts = str(int(time.time() * 1000))
    client.post(f"/api/push/{key}", json={
        "type": "heartbeat", "battery": "50%", "device": "Redmi-K60", "timestamp": ts,
    })
    devices = client.get("/api/devices", headers=auth).json()["items"]
    assert any(d["device_key"] == "Redmi-K60" for d in devices)
