"""多设备与 SIM 卡管理测试"""
import time

from app.app_settings import set_setting


def _mk_token(client):
    r = client.post("/api/setup/admin", json={"username": "admin", "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _push(client, device, sim, sender, content, mtype="sms"):
    ts = str(int(time.time() * 1000))
    return client.post("/api/webhook", json={
        "type": mtype, "from": sender, "content": content,
        "sim": sim, "device": device, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": ts,
    })


def test_auto_register_and_rename(client):
    _push(client, "OPPO-PBAM00", "SIM1_13800000000", "10086", "短信A")
    _push(client, "OPPO-PBAM00", "SIM2_15013303441", "10010", "短信B")
    _push(client, "Redmi-K60", "SIM1_13911112222", "10086", "短信C")

    headers = _mk_token(client)
    devices = client.get("/api/devices", headers=headers).json()["items"]
    assert len(devices) == 2, "应自动发现两台设备"
    by_key = {d["device_key"]: d for d in devices}
    assert by_key["OPPO-PBAM00"]["sms_total"] == 2
    assert by_key["Redmi-K60"]["sms_total"] == 1

    # 重命名设备
    r = client.put(f"/api/devices/{by_key['OPPO-PBAM00']['id']}",
                   headers=headers, json={"name": "我的旧手机", "note": "转发机"})
    assert r.status_code == 200
    devices = client.get("/api/devices", headers=headers).json()["items"]
    assert any(d["name"] == "我的旧手机" for d in devices)


def test_sim_management(client):
    _push(client, "OPPO-PBAM00", "SIM1_13800000000", "10086", "短信A")
    _push(client, "OPPO-PBAM00", "SIM1_13800000000", "106", "短信D")
    _push(client, "OPPO-PBAM00", "SIM2_15013303441", "10010", "短信B")

    headers = _mk_token(client)
    devices = client.get("/api/devices", headers=headers).json()["items"]
    oppo = next(d for d in devices if d["device_key"] == "OPPO-PBAM00")
    assert oppo["sim_count"] == 2

    sims = client.get(f"/api/devices/{oppo['id']}/sims", headers=headers).json()["items"]
    by_slot = {s["slot_key"]: s for s in sims}
    assert by_slot["SIM1_13800000000"]["number"] == "13800000000"
    assert by_slot["SIM1_13800000000"]["msg_count"] == 2

    # SIM 重命名后按 SIM 筛选消息
    sid = by_slot["SIM1_13800000000"]["id"]
    client.put(f"/api/sims/{sid}", headers=headers, json={"alias": "主卡", "note": ""})
    msgs = client.get(f"/api/messages?type=sms&sim_id={sid}", headers=headers).json()
    assert msgs["total"] == 2

    # 按设备筛选
    msgs = client.get(f"/api/messages?type=sms&device_id={oppo['id']}", headers=headers).json()
    assert msgs["total"] == 3

    # 删除 SIM 后其消息保留（sim_id 置空）
    client.delete(f"/api/sims/{sid}", headers=headers)
    sims = client.get(f"/api/devices/{oppo['id']}/sims", headers=headers).json()["items"]
    assert len(sims) == 1
    msgs = client.get(f"/api/messages?type=sms&device_id={oppo['id']}", headers=headers).json()
    assert msgs["total"] == 3


def test_delete_device_cascades(client):
    _push(client, "Redmi-K60", "SIM1_13911112222", "10086", "短信C")
    headers = _mk_token(client)
    devices = client.get("/api/devices", headers=headers).json()["items"]
    redmi = next(d for d in devices if d["device_key"] == "Redmi-K60")
    r = client.delete(f"/api/devices/{redmi['id']}", headers=headers)
    assert r.status_code == 200
    msgs = client.get("/api/messages?type=sms", headers=headers).json()
    assert msgs["total"] == 0, "删除设备应级联删除其消息"
    assert client.get("/api/devices", headers=headers).json()["items"] == []


def test_summary_per_device(client):
    _push(client, "OPPO-PBAM00", "SIM1_13800000000", "10086", "短信A")
    _push(client, "Redmi-K60", "SIM1_13911112222", "10086", "短信C")
    _push(client, "Redmi-K60", "SIM1_13911112222", "02195588", "未接来电", mtype="call")
    headers = _mk_token(client)
    devices = client.get("/api/devices", headers=headers).json()["items"]
    redmi = next(d for d in devices if d["device_key"] == "Redmi-K60")
    s = client.get(f"/api/stats/summary?device_id={redmi['id']}", headers=headers).json()
    assert s["sms_total"] == 1 and s["call_total"] == 1
    g = client.get("/api/stats/summary", headers=headers).json()
    assert g["sms_total"] == 2 and g["call_total"] == 1
