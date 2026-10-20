"""设备状态与工作时长核心逻辑（多设备版）"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..app_settings import get_setting, offline_threshold_minutes
from ..models import Device, DeviceEvent, Heartbeat
from .registry import device_display_name


def get_current_state(db: Session, device_id: int) -> dict:
    """指定设备的当前状态：online/offline、最后心跳、当前电量"""
    last: Heartbeat | None = (
        db.query(Heartbeat).filter(Heartbeat.device_id == device_id)
        .order_by(Heartbeat.ts.desc()).first()
    )
    if not last:
        return {"online": False, "last_heartbeat": None, "battery_pct": None,
                "plugged": False, "battery_info": "", "threshold_minutes": offline_threshold_minutes(db)}
    threshold = timedelta(minutes=offline_threshold_minutes(db))
    online = datetime.now() - last.ts <= threshold
    return {
        "online": online,
        "last_heartbeat": last.ts.isoformat(sep=" ", timespec="seconds"),
        "battery_pct": last.battery_pct,
        "plugged": last.plugged,
        "battery_info": last.battery_info,
        "threshold_minutes": offline_threshold_minutes(db),
    }


def register_heartbeat(db: Session, device_id: int, ts: datetime, battery_pct,
                       plugged: bool, battery_info: str) -> str | None:
    """记录心跳，返回状态变化（online）或 None"""
    prev = get_current_state(db, device_id)
    hb = Heartbeat(ts=ts, battery_pct=battery_pct, plugged=plugged,
                   battery_info=battery_info, device_id=device_id, dedup_key="")
    db.add(hb)

    state_change = None
    if not prev["online"]:
        state_change = "online"
        db.add(DeviceEvent(ts=datetime.now(), device_id=device_id,
                           state="online", battery_pct=battery_pct))

    db.flush()
    hb.dedup_key = f"hb-{device_id}-{int(ts.timestamp() * 1000)}-{hb.id}"
    return state_change


def mark_offline_if_needed(db: Session) -> list[dict]:
    """周期检查所有出现过心跳的设备：超阈值未心跳判离线，返回广播事件列表"""
    events = []
    threshold = timedelta(minutes=offline_threshold_minutes(db))
    now = datetime.now()

    device_ids = [r[0] for r in db.query(Heartbeat.device_id).distinct().all() if r[0] is not None]
    for did in device_ids:
        last: Heartbeat | None = (
            db.query(Heartbeat).filter(Heartbeat.device_id == did)
            .order_by(Heartbeat.ts.desc()).first()
        )
        if not last or now - last.ts <= threshold:
            continue
        last_event = (
            db.query(DeviceEvent).filter(DeviceEvent.device_id == did)
            .order_by(DeviceEvent.ts.desc()).first()
        )
        if last_event and last_event.state == "offline":
            continue
        dev = db.get(Device, did)
        db.add(DeviceEvent(ts=now, device_id=did, state="offline",
                           battery_pct=last.battery_pct))
        events.append({
            "event": "device_offline", "device_id": did,
            "device_name": device_display_name(dev),
            "ts": now.isoformat(sep=" ", timespec="seconds"),
            "battery_pct": last.battery_pct,
        })
    return events


def working_seconds(db: Session, device_id: int, day: datetime | None = None) -> int:
    """指定设备的工作时长（秒）：按心跳序列还原在线区间累计"""
    q = db.query(Heartbeat).filter(Heartbeat.device_id == device_id).order_by(Heartbeat.ts)
    if day:
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        q = q.filter(Heartbeat.ts >= start, Heartbeat.ts < end)
    hbs: list[Heartbeat] = q.all()
    if not hbs:
        return 0

    threshold = timedelta(minutes=offline_threshold_minutes(db))
    interval = timedelta(minutes=int(get_setting("heartbeat_interval_min", db=db) or 5))
    now = datetime.now()
    state = get_current_state(db, device_id)

    total = 0.0
    seg_start = hbs[0].ts
    prev_ts = hbs[0].ts
    for hb in hbs[1:]:
        if hb.ts - prev_ts > threshold:
            total += (prev_ts - seg_start).total_seconds() + interval.total_seconds()
            seg_start = hb.ts
        prev_ts = hb.ts

    if state["online"] and (not day or day.date() == now.date()):
        if now - prev_ts <= threshold:
            total += (now - seg_start).total_seconds()
        else:
            total += (prev_ts - seg_start).total_seconds() + interval.total_seconds()
    else:
        total += (prev_ts - seg_start).total_seconds() + interval.total_seconds()
    return int(total)


def background_offline_checker():
    """后台任务：周期检查各设备离线"""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        return mark_offline_if_needed(db)
    finally:
        db.commit()
        db.close()
