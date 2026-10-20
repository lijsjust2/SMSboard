from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Setting(Base):
    """键值配置：管理员账号、webhook secret、pushplus 推送配置等"""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Device(Base):
    """设备：以 SmsForwarder 的设备标记（device_mark）自动发现，可重命名备注"""
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("device_key", name="uq_device_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_key: Mapped[str] = mapped_column(String(64))  # 原始 device_mark
    name: Mapped[str] = mapped_column(String(64), default="")  # 用户自定义别名
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Sim(Base):
    """SIM 卡：归属设备，依据消息中的卡槽信息自动发现，可重命名备注"""
    __tablename__ = "sims"
    __table_args__ = (
        UniqueConstraint("device_id", "slot_key", name="uq_sim_device_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    slot_key: Mapped[str] = mapped_column(String(64))  # 原始卡槽标识，如 SIM1_15013303441
    slot_label: Mapped[str] = mapped_column(String(16), default="")  # SIM1 / SIM2
    number: Mapped[str] = mapped_column(String(32), default="")  # 解析出的号码
    alias: Mapped[str] = mapped_column(String(64), default="")  # 用户自定义别名
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Message(Base):
    """收到的转发消息（短信/通话）"""
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="uq_message_dedup"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(16), index=True)  # sms / call
    sender: Mapped[str] = mapped_column(String(64), default="")  # 发件号码 / 来电号码
    content: Mapped[str] = mapped_column(Text, default="")
    sim_slot: Mapped[str] = mapped_column(String(64), default="")  # 原始卡槽信息
    device: Mapped[str] = mapped_column(String(64), default="")  # 原始设备标记
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), index=True, nullable=True)
    sim_id: Mapped[int | None] = mapped_column(ForeignKey("sims.id"), index=True, nullable=True)
    receive_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    dedup_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Heartbeat(Base):
    """心跳帧：在线判定 + 电量历史"""
    __tablename__ = "heartbeats"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="uq_heartbeat_dedup"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    plugged: Mapped[bool] = mapped_column(Boolean, default=False)
    battery_info: Mapped[str] = mapped_column(String(128), default="")
    device: Mapped[str] = mapped_column(String(64), default="")  # 原始设备标记
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), index=True, nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(64))


class DeviceEvent(Base):
    """设备在线/离线状态变化事件"""
    __tablename__ = "device_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    device_id: Mapped[int] = mapped_column(Integer, index=True)
    state: Mapped[str] = mapped_column(String(16))  # online / offline
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
