import asyncio
import os

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .auth import verify_jwt
from .database import Base, engine
from .routers import devices as devices_router
from .routers import settings as settings_router
from .routers import setup as setup_router
from .routers import stats as stats_router
from .routers import webhook as webhook_router
from .services.device_state import background_offline_checker
from .services.pushplus import close_client, notify_device_state
from .ws import manager

app = FastAPI(title="SmsBoard", docs_url=None, redoc_url=None)


def _migrate_old_db():
    """为早期版本库补充新列（幂等）"""
    from sqlalchemy import text
    stmts = [
        "ALTER TABLE messages ADD COLUMN device_id INTEGER",
        "ALTER TABLE messages ADD COLUMN sim_id INTEGER",
        "ALTER TABLE heartbeats ADD COLUMN device_id INTEGER",
        "ALTER TABLE device_events ADD COLUMN device_id INTEGER",
    ]
    with engine.begin() as conn:
        for s in stmts:
            try:
                conn.execute(text(s))
            except Exception:
                pass


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(engine)
    _migrate_old_db()


app.include_router(setup_router.router)
app.include_router(webhook_router.router)
app.include_router(devices_router.router)
app.include_router(stats_router.router)
app.include_router(settings_router.router)

# 挂载前端构建产物（存在时）
if os.path.isdir(config.FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(config.FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str, request: Request):
        file = os.path.join(config.FRONTEND_DIST, path)
        if path and os.path.isfile(file):
            return FileResponse(file)
        return FileResponse(os.path.join(config.FRONTEND_DIST, "index.html"))


async def _offline_loop():
    """每 30 秒检查各设备离线；广播并按配置推送 pushplus 告警"""
    while True:
        await asyncio.sleep(30)
        try:
            events = await asyncio.to_thread(background_offline_checker)
            for ev in events or []:
                await manager.broadcast(ev)
                await notify_device_state("offline", ev.get("device_name", "未知设备"),
                                          ev.get("battery_pct"))
        except Exception:
            pass


@app.on_event("startup")
async def start_background():
    app.state.offline_task = asyncio.create_task(_offline_loop())


@app.on_event("shutdown")
async def on_shutdown():
    app.state.offline_task.cancel()
    await close_client()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = ""):
    payload = verify_jwt(token)
    if not payload:
        await ws.close(code=4401)
        return
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # 保活
    except WebSocketDisconnect:
        manager.disconnect(ws)
