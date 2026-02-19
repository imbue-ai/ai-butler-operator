import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.screenshot_streamer import send_status

logger = logging.getLogger(__name__)

router = APIRouter()

# session_manager is injected at startup from main.py
session_manager = None


@router.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str):
    session = session_manager.get_session(code) if session_manager else None
    if session is None:
        await websocket.close(4004, "Invalid session code")
        return

    await websocket.accept()
    session.websocket = websocket
    logger.info("WebSocket connected for session %s", code)

    await send_status(websocket, session.state.value)

    try:
        while True:
            # Keep connection alive; handle pings from client
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except (WebSocketDisconnect, asyncio.TimeoutError):
        logger.info("WebSocket disconnected for session %s", code)
    except Exception:
        logger.exception("WebSocket error for session %s", code)
    finally:
        if session.websocket is websocket:
            session.websocket = None
