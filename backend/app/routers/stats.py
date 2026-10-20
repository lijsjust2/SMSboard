"""看板数据接口：统计、记录、电量、设备状态（支持设备/SIM 筛选）"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..app_settings import offline_threshold_minutes
from ..auth import get_current_user
from ..database import get_db
from ..models import Device, DeviceEvent, Heartbeat, Message
from ..services.device_state import get_current_state, working_seconds

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.delete("/api/messages/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db)):
    """删除单条短信/通话记录"""
    m = db.get(Message, message_id)
    if not m:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(m)
    db.commit()
    return {"code": 200, "msg": "ok"}


def _day_start(day: datetime | None) -> datetime:
    base = day or datetime.now()
    return base.replace(hour=0, minute=0, second=0, microsecond=0)


def _device_or_none(db: Session, device_id: int | None) -> Device | None:
    if device_id is None:
        return None
    return db.get(Device, device_id)


@router.get("/api/stats/summary")
def summary(device_id: int | None = None, db: Session = Depends(get_db)):
    today_start = _day_start(None)
    total_start = datetime(2000, 1, 1)

    def count(msg_type: str, since: datetime) -> int:
        q = db.query(func.count(Message.id)).filter(
            Message.type == msg_type, Message.receive_time >= since)
        if device_id is not None:
            q = q.filter(Message.device_id == device_id)
        return q.scalar() or 0

    def work(day: datetime | None) -> int:
        if device_id is not None:
            return working_seconds(db, device_id, day)
        ids = [r[0] for r in db.query(Device.id).all()]
        return sum(working_seconds(db, d, day) for d in ids)

    if device_id is not None:
        state = get_current_state(db, device_id)
        online, battery, plugged = state["online"], state["battery_pct"], state["plugged"]
    else:
        devices = db.query(Device.id).all()
        states = [get_current_state(db, d[0]) for d in devices]
        online = any(s["online"] for s in states)
        latest = (
            db.query(Heartbeat).filter(Heartbeat.battery_pct.isnot(None))
            .order_by(Heartbeat.ts.desc()).first()
        )
        battery = latest.battery_pct if latest else None
        plugged = latest.plugged if latest else False

    last_q = db.query(Message)
    if device_id is not None:
        last_q = last_q.filter(Message.device_id == device_id)
    m = last_q.order_by(Message.receive_time.desc()).first()

    return {
        "code": 200,
        "device_id": device_id,
        "sms_total": count("sms", total_start),
        "sms_today": count("sms", today_start),
        "call_total": count("call", total_start),
        "call_today": count("call", today_start),
        "online_now": online,
        "battery_pct": battery,
        "plugged": plugged,
        "working_seconds_today": work(datetime.now()),
        "working_seconds_total": work(None),
        "last_message": {
            "type": m.type, "sender": m.sender, "content": m.content,
            "receive_time": m.receive_time.isoformat(sep=" ", timespec="seconds"),
        } if m else None,
    }


@router.get("/api/messages")
def messages(
    type: str = Query("sms", pattern="^(sms|call)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=128),
    start: str = Query("", max_length=19),
    end: str = Query("", max_length=19),
    device_id: int | None = None,
    sim_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Message).filter(Message.type == type)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((Message.sender.like(like)) | (Message.content.like(like)))
    if start:
        try:
            q = q.filter(Message.receive_time >= datetime.strptime(start, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass
    if end:
        try:
            q = q.filter(Message.receive_time <= datetime.strptime(end, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass
    if device_id is not None:
        q = q.filter(Message.device_id == device_id)
    if sim_id is not None:
        q = q.filter(Message.sim_id == sim_id)
    total = q.count()
    rows = (
        q.order_by(Message.receive_time.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "code": 200, "total": total, "page": page, "size": size,
        "items": [
            {
                "id": r.id, "sender": r.sender, "content": r.content,
                "sim_slot": r.sim_slot, "device": r.device, "device_id": r.device_id,
                "sim_id": r.sim_id,
                "receive_time": r.receive_time.isoformat(sep=" ", timespec="seconds"),
            }
            for r in rows
        ],
    }


@router.get("/api/battery/history")
def battery_history(hours: int = Query(24, ge=1, le=720), device_id: int | None = None,
                    db: Session = Depends(get_db)):
    since = datetime.now() - timedelta(hours=hours)
    q = db.query(Heartbeat).filter(
        Heartbeat.ts >= since, Heartbeat.battery_pct.isnot(None))
    if device_id is not None:
        q = q.filter(Heartbeat.device_id == device_id)
    rows = q.order_by(Heartbeat.ts).all()
    return {
        "code": 200,
        "items": [
            {
                "ts": r.ts.isoformat(sep=" ", timespec="minutes"),
                "battery_pct": r.battery_pct,
                "plugged": r.plugged,
                "device_id": r.device_id,
            }
            for r in rows
        ],
    }


@router.get("/api/device/status")
def device_status(device_id: int, db: Session = Depends(get_db)):
    """指定设备的当前状态、最近 50 次心跳与状态变化事件"""
    dev = _device_or_none(db, device_id)
    if dev is None:
        return {"code": 404, "detail": "设备不存在"}
    state = get_current_state(db, device_id)
    events = (
        db.query(DeviceEvent).filter(DeviceEvent.device_id == device_id)
        .order_by(DeviceEvent.ts.desc()).limit(30).all()
    )
    heartbeats = (
        db.query(Heartbeat).filter(Heartbeat.device_id == device_id)
        .order_by(Heartbeat.ts.desc()).limit(50).all()
    )
    return {
        "code": 200,
        "device": {"id": dev.id, "name": dev.name or dev.device_key, "device_key": dev.device_key},
        "current": state,
        "heartbeats": [
            {
                "ts": h.ts.isoformat(sep=" ", timespec="seconds"),
                "battery_pct": h.battery_pct,
                "plugged": h.plugged,
                "battery_info": h.battery_info,
            }
            for h in heartbeats
        ],
        "events": [
            {
                "ts": e.ts.isoformat(sep=" ", timespec="seconds"),
                "state": e.state,
                "battery_pct": e.battery_pct,
            }
            for e in events
        ],
    }


@router.get("/api/stats/hourly")
def hourly(days: int = Query(7, ge=1, le=90), device_id: int | None = None,
           db: Session = Depends(get_db)):
    """近 N 天消息的小时分布（活跃时段）"""
    since = _day_start(None) - timedelta(days=days - 1)
    q = db.query(
        func.strftime("%H", Message.receive_time).label("hour"),
        Message.type,
        func.count(Message.id),
    ).filter(Message.receive_time >= since)
    if device_id is not None:
        q = q.filter(Message.device_id == device_id)
    rows = q.group_by("hour", Message.type).all()
    out = {"sms": [0] * 24, "call": [0] * 24}
    for hour, mtype, cnt in rows:
        if mtype in out:
            out[mtype][int(hour)] = cnt
    return {"code": 200, "days": days, "hourly": out}


@router.get("/api/stats/daily")
def daily(days: int = Query(7, ge=1, le=90), device_id: int | None = None,
          db: Session = Depends(get_db)):
    """近 N 天每日短信/通话数量 + 工作时长"""
    result = []
    today = _day_start(None)
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        nxt = day + timedelta(days=1)

        def cnt(msg_type: str) -> int:
            q = db.query(func.count(Message.id)).filter(
                Message.type == msg_type, Message.receive_time >= day,
                Message.receive_time < nxt)
            if device_id is not None:
                q = q.filter(Message.device_id == device_id)
            return q.scalar() or 0

        if device_id is not None:
            wsec = working_seconds(db, device_id, day)
        else:
            wsec = sum(working_seconds(db, d[0], day) for d in db.query(Device.id).all())

        result.append({
            "date": day.strftime("%m-%d"),
            "sms": cnt("sms"),
            "call": cnt("call"),
            "working_minutes": round(wsec / 60),
        })
    return {"code": 200, "items": result, "threshold_minutes": offline_threshold_minutes(db)}
