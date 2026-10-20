"""设备管理与 SIM 卡管理"""
import pydantic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..app_settings import offline_threshold_minutes
from ..auth import get_current_user
from ..database import get_db
from ..models import Device, Heartbeat, Message, Sim
from ..services.device_state import get_current_state, working_seconds
from ..services.registry import device_display_name

router = APIRouter(dependencies=[Depends(get_current_user)])


class DeviceBody(pydantic.BaseModel):
    name: str = ""
    note: str = ""


class SimBody(pydantic.BaseModel):
    alias: str = ""
    note: str = ""
    number: str = ""


@router.get("/api/devices")
def list_devices(db: Session = Depends(get_db)):
    """设备列表：含在线状态、电量、统计、SIM 卡数与工作时长"""
    devices = db.query(Device).order_by(Device.created_at).all()
    out = []
    for d in devices:
        state = get_current_state(db, d.id)
        today_start = func_date_start()
        out.append({
            "id": d.id,
            "device_key": d.device_key,
            "name": d.name or d.device_key,
            "note": d.note,
            "online": state["online"],
            "battery_pct": state["battery_pct"],
            "plugged": state["plugged"],
            "last_heartbeat": state["last_heartbeat"],
            "working_seconds_today": working_seconds(db, d.id, today_start),
            "working_seconds_total": working_seconds(db, d.id),
            "sms_total": _count(db, d.id, "sms"),
            "call_total": _count(db, d.id, "call"),
            "sim_count": db.query(func.count(Sim.id)).filter(Sim.device_id == d.id).scalar() or 0,
        })
    return {
        "code": 200,
        "items": out,
        "threshold_minutes": offline_threshold_minutes(db),
    }


def func_date_start():
    from datetime import datetime
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _count(db: Session, device_id: int, msg_type: str) -> int:
    return (
        db.query(func.count(Message.id))
        .filter(Message.device_id == device_id, Message.type == msg_type)
        .scalar() or 0
    )


@router.put("/api/devices/{device_id}")
def update_device(device_id: int, body: DeviceBody, db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(status_code=404, detail="设备不存在")
    d.name = body.name.strip() or d.device_key
    d.note = body.note
    db.commit()
    return {"code": 200, "msg": "ok"}


@router.delete("/api/devices/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    """删除设备及其 SIM 卡与全部相关数据"""
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(status_code=404, detail="设备不存在")
    db.query(Message).filter(Message.device_id == device_id).delete()
    db.query(Heartbeat).filter(Heartbeat.device_id == device_id).delete()
    db.query(Sim).filter(Sim.device_id == device_id).delete()
    db.query(Device).filter(Device.id == device_id).delete()
    db.commit()
    return {"code": 200, "msg": "ok"}


@router.get("/api/devices/{device_id}/sims")
def list_sims(device_id: int, db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(status_code=404, detail="设备不存在")
    sims = db.query(Sim).filter(Sim.device_id == device_id).order_by(Sim.slot_key).all()
    return {
        "code": 200,
        "device": {"id": d.id, "name": device_display_name(d)},
        "items": [
            {
                "id": s.id, "slot_key": s.slot_key, "slot_label": s.slot_label,
                "number": s.number, "alias": s.alias, "note": s.note,
                "msg_count": db.query(func.count(Message.id)).filter(Message.sim_id == s.id).scalar() or 0,
            }
            for s in sims
        ],
    }


@router.put("/api/sims/{sim_id}")
def update_sim(sim_id: int, body: SimBody, db: Session = Depends(get_db)):
    s = db.get(Sim, sim_id)
    if not s:
        raise HTTPException(status_code=404, detail="SIM 卡不存在")
    s.alias = body.alias.strip()
    s.note = body.note
    s.number = body.number.strip()
    db.commit()
    return {"code": 200, "msg": "ok"}


@router.delete("/api/sims/{sim_id}")
def delete_sim(sim_id: int, db: Session = Depends(get_db)):
    s = db.get(Sim, sim_id)
    if not s:
        raise HTTPException(status_code=404, detail="SIM 卡不存在")
    db.query(Message).filter(Message.sim_id == sim_id).update({Message.sim_id: None})
    db.delete(s)
    db.commit()
    return {"code": 200, "msg": "ok"}
