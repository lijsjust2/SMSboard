"""兼容 SmsForwarder 消息模板为空时的默认表单格式"""
import time

import pytest


@pytest.fixture()
def auth(client):
    r = client.post("/api/setup/admin", json={"username": "admin", "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_form_encoded_default_body(client, auth):
    """App 消息模板留空时默认发送 from=xx&content=xx&timestamp=xx（表单格式）"""
    key = client.get("/api/settings", headers=auth).json()["push_key"]
    r = client.post(
        f"/api/push/{key}",
        content=f"from=10086&content=%E6%B5%8B%E8%AF%95%E7%9F%AD%E4%BF%A1&timestamp={int(time.time() * 1000)}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, f"表单格式推送失败: {r.text}"
    msgs = client.get("/api/messages?type=sms", headers=auth).json()
    assert msgs["total"] == 1 and msgs["items"][0]["sender"] == "10086"
    # 无 device 字段 → 归入默认设备
    devices = client.get("/api/devices", headers=auth).json()["items"]
    assert any(d["device_key"] == "未命名设备" for d in devices)


def test_bad_body_returns_http_400(client, auth):
    """坏请求必须返回 HTTP 400（而非 200），让 App 测试如实报错"""
    key = client.get("/api/settings", headers=auth).json()["push_key"]
    r = client.post(f"/api/push/{key}", content=b"\xff\xfe garbage",
                    headers={"Content-Type": "text/plain"})
    assert r.status_code == 400


def test_invalid_key_returns_http_403(client, auth):
    r = client.post("/api/push/wrongkey", json={"type": "sms", "from": "1", "content": "x"})
    assert r.status_code == 403
