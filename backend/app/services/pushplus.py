"""PushPlus 推送：设备离线/上线告警"""
import httpx

from .. import config
from ..app_settings import get_setting

http_client = httpx.AsyncClient(timeout=10.0)


async def pushplus_notify(title: str, content: str, db=None) -> bool:
    token = get_setting("pushplus_token", db=db)
    if not token:
        return False
    try:
        resp = await http_client.post(
            config.PUSHPLUS_API,
            json={"token": token, "title": title, "content": content, "template": "html"},
        )
        return resp.status_code == 200 and '"code":200' in resp.text
    except Exception:
        return False


async def notify_device_state(state: str, device_name: str, battery, db=None):
    """设备状态变化时按用户配置决定是否推送"""
    if state == "offline" and get_setting("notify_on_offline", db=db) == "true":
        battery_txt = f"，最后电量 {battery}%" if battery is not None else ""
        return await pushplus_notify(
            f"⚠️ 设备离线：{device_name}",
            f"设备「{device_name}」超过离线阈值未收到心跳，已判定为离线{battery_txt}。"
            f"请检查手机网络、SmsForwarder 是否被系统查杀，或充电/流量是否正常。",
            db=db,
        )
    if state == "online" and get_setting("notify_on_online", db=db) == "true":
        battery_txt = f"，当前电量 {battery}%" if battery is not None else ""
        return await pushplus_notify(
            f"✅ 设备上线：{device_name}", f"设备「{device_name}」心跳已恢复{battery_txt}。", db=db
        )
    return None


async def close_client():
    await http_client.aclose()
