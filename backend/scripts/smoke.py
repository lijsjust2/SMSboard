"""端到端冒烟测试：对运行中的 SmsBoard 服务模拟 SmsForwarder 推送
用法: python scripts/smoke.py [base_url]   (默认 http://localhost:9990)
"""
import base64
import hashlib
import hmac
import sys
import time
from urllib.parse import quote

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9990"
SECRET = "smoke-secret"


def make_sign(ts: str) -> str:
    sts = f"{ts}\n{SECRET}"
    return quote(base64.b64encode(hmac.new(SECRET.encode(), sts.encode(), hashlib.sha256).digest()).decode())


def main():
    c = httpx.Client(base_url=BASE, timeout=10)
    # SPA 首页
    r = c.get("/")
    assert r.status_code == 200 and "<div id=\"app\">" in r.text, "SPA 首页异常"

    status = c.get("/api/setup/status").json()
    if status["need_setup"]:
        r = c.post("/api/setup/admin", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, f"初始化失败: {r.text}"
        print("[OK] 首次初始化管理员完成")
    token = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json().get("token")
    assert token, "登录失败"
    H = {"Authorization": f"Bearer {token}"}
    print("[OK] 登录成功")

    # 配置 secret（模拟用户在设置页配置）
    r = c.put("/api/settings", headers=H, json={"webhook_secret": SECRET, "pushplus_token": "",
                                     "notify_on_offline": True, "notify_on_online": False,
                                     "heartbeat_interval_min": 5, "offline_threshold_min": 15})
    assert r.status_code == 200, f"设置失败: {r.text}"
    print("[OK] 配置 webhook secret")

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    ts = str(int(time.time() * 1000))
    # Bark 式 Key 推送（读设置页生成的 key）
    key = c.get("/api/settings", headers=H).json()["push_key"]
    assert key, "push_key 未生成"
    r = c.post(f"/api/push/{key}", json={
        "type": "sms", "from": "10688514111669", "content": "【联通在线】验证码：888888",
        "sim": "SIM2_15013303441", "device": "OPPO-PBAM00", "time": now, "timestamp": ts,
    })
    assert r.json()["code"] == 200, f"Key 推送短信失败: {r.text}"
    print("[OK] Bark式Key推送短信 → 入库")

    # 错误 Key
    bad_key = c.post("/api/push/0000000000000000", json={
        "type": "sms", "from": "x", "content": "x", "timestamp": ts,
    })
    assert bad_key.json()["code"] == 403, "错误 Key 未被拒绝"
    print("[OK] 错误推送Key被拒绝 (403)")

    # 签名方式通话
    ts = str(int(time.time() * 1000))
    r = c.post("/api/webhook", json={
        "type": "call", "from": "02195588", "content": "未接来电",
        "sim": "SIM1_15013303441", "device": "OPPO-PBAM00", "time": now,
        "timestamp": ts, "sign": make_sign(ts),
    })
    assert r.json()["code"] == 200, f"通话推送失败: {r.text}"
    print("[OK] 带签名通话推送 → 入库")

    # 心跳
    ts = str(int(time.time() * 1000))
    r = c.post(f"/api/push/{key}", json={
        "type": "heartbeat", "battery": "86%", "plugged": "充电中", "info": "86% - 充电中",
        "device": "OPPO-PBAM00", "time": now, "timestamp": ts,
    })
    assert r.json()["code"] == 200, f"心跳失败: {r.text}"
    print("[OK] 心跳推送 → 设备在线")

    s = c.get("/api/stats/summary", headers=H).json()
    assert s["sms_total"] >= 1 and s["call_total"] >= 1, "统计异常"
    assert s["online_now"] is True and s["battery_pct"] == 86.0, "状态异常"
    print(f"[OK] 统计: 短信{s['sms_total']} 电话{s['call_total']} "
          f"今日工作{s['working_seconds_today']}s 电量{s['battery_pct']}%")

    bad = c.post("/api/webhook", json={
        "type": "sms", "from": "x", "content": "x", "timestamp": ts, "sign": make_sign("wrong"),
    })
    assert bad.json()["code"] == 403, "错误签名未被拒绝"
    print("[OK] 错误签名被拒绝 (403)")

    # 设备管理与 SIM 卡
    devices = c.get("/api/devices", headers=H).json()["items"]
    dev = next((d for d in devices if d["device_key"] == "OPPO-PBAM00"), None)
    assert dev, "设备未被自动发现"
    sims = c.get(f"/api/devices/{dev['id']}/sims", headers=H).json()["items"]
    assert any(s["slot_key"] == "SIM2_15013303441" for s in sims), "SIM 卡未被自动发现"
    r = c.put(f"/api/devices/{dev['id']}", headers=H, json={"name": "测试机", "note": ""})
    assert r.status_code == 200
    s2 = c.get(f"/api/stats/summary?device_id={dev['id']}", headers=H).json()
    assert s2["battery_pct"] == 86.0 and s2["online_now"], "按设备统计异常"
    print(f"[OK] 设备管理: 发现设备「{dev['device_key']}」SIM卡{len(sims)}张, 按设备统计正常")

    print("\n=== 全部冒烟检查通过 ===")


if __name__ == "__main__":
    main()
