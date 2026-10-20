import os
import sys
import tempfile

import pytest

# 独立临时数据库，避免污染真实数据
_tmpdir = tempfile.mkdtemp()
os.environ["SMSBOARD_DB"] = os.path.join(_tmpdir, "test.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.app_settings import set_setting  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_settings():
    """每个用例前清空设置表，避免用例间相互污染"""
    from app.database import Base, engine
    Base.metadata.create_all(engine)
    from app.models import (Device, DeviceEvent, Heartbeat, Message, Setting,
                            Sim)
    s = SessionLocal()
    try:
        for model in (Message, Heartbeat, DeviceEvent, Sim, Device, Setting):
            s.query(model).delete()
        s.commit()
    finally:
        s.close()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def with_admin(db):
    set_setting("admin_username", "admin", db=db)
    set_setting("admin_password_hash", "x", db=db)  # 只为标记已初始化
    return db
