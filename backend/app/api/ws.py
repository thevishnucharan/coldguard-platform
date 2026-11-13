"""WebSocket real-time channel.

Browsers cannot set Authorization headers on WebSocket upgrades, so the client sends the
access token as the FIRST message ({"type":"auth","token":...}) — never in the URL, which
would leak into proxy logs. Events are filtered by the user's facility scope; per-user
notifications are delivered only to their recipients. Server sends a heartbeat every 25 s.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.metrics import WS_CONNECTIONS
from app.db.session import SessionLocal
from app.services.access import resolve_scope
from app.services.realtime import hub

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=10)
        token = json.loads(first).get("token", "")
    except Exception:
        await ws.close(code=4401)
        return
    db = SessionLocal()
    try:
        from app.api.deps import user_from_token
        user = user_from_token(db, token)
        scope = resolve_scope(db, user)
    except Exception:
        await ws.close(code=4401)
        return
    finally:
        db.close()
    allowed = {str(f) for f in scope.facility_ids}
    uid = str(user.id)
    sub = hub.subscribe(asyncio.get_running_loop())
    WS_CONNECTIONS.inc()
    await ws.send_json({"type": "hello", "data": {"user": user.name, "global": scope.is_global}})

    async def pump():
        while True:
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
                continue
            if event.get("user_ids") is not None and uid not in event["user_ids"]:
                continue
            fid = event.get("facility_id")
            if fid and not scope.is_global and fid not in allowed:
                continue
            await ws.send_json({k: v for k, v in event.items() if k not in ("origin", "user_ids")})

    async def reader():
        while True:
            await ws.receive_text()  # client pongs / keep-alives

    tasks = [asyncio.create_task(pump()), asyncio.create_task(reader())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        hub.unsubscribe(sub)
        WS_CONNECTIONS.dec()
