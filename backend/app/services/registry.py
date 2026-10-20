"""设备/SIM 卡自动发现与注册"""
import re

from sqlalchemy.orm import Session

from ..models import Device, Sim


def extract_phone_number(text: str) -> str:
    """从卡槽备注文本中提取号码：优先 11 位手机号，其次任意 ≥4 位的连续数字串"""
    if not text:
        return ""
    m = re.search(r"\d{11}", text)
    if m:
        return m.group()
    m = re.search(r"\d{4,}", text)
    return m.group() if m else ""


def ensure_device(db: Session, device_str: str) -> Device | None:
    """按 device_mark 自动注册设备；空标记返回 None（归入未知设备语义）"""
    key = (device_str or "").strip()
    if not key:
        return None
    dev = db.query(Device).filter(Device.device_key == key).first()
    if not dev:
        dev = Device(device_key=key, name=key)
        db.add(dev)
        db.flush()
    return dev


def parse_sim_key(sim_str: str) -> tuple[str, str]:
    """'SIM1_15013303441' → ('SIM1', '15013303441')；无法解析时整体作为 slot"""
    s = (sim_str or "").strip()
    if not s:
        return "", ""
    if "_" in s:
        slot, _, number = s.partition("_")
        return slot or "SIM", number.strip()
    return s, ""


def ensure_sim(db: Session, device: Device, sim_str: str) -> Sim | None:
    """按 (device, 卡槽标识) 自动注册 SIM 卡；号码从备注文本中智能提取"""
    if device is None:
        return None
    s = (sim_str or "").strip()
    if not s:
        return None
    sim = db.query(Sim).filter(Sim.device_id == device.id, Sim.slot_key == s).first()
    if not sim:
        slot_label, number = parse_sim_key(s)
        sim = Sim(device_id=device.id, slot_key=s, slot_label=slot_label, number=number)
        db.add(sim)
        db.flush()
    if not sim.number:
        # 备注混有其他文字时提取其中的号码，如 "测试选项项_18888888888" → 18888888888
        _, tail = parse_sim_key(s)
        sim.number = extract_phone_number(tail) or sim.number
    return sim


def device_display_name(dev: Device | None) -> str:
    if dev is None:
        return "未知设备"
    return dev.name or dev.device_key
