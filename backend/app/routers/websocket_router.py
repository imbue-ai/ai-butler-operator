import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.ws_messages import pong_message, status_message

logger = logging.getLogger(__name__)

router = APIRouter()

# session_manager is injected at startup from main.py
session_manager = None


@router.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str):
    session = session_manager.get_session(code) if session_manager else None
    await websocket.accept()
    if session is None:
        await websocket.close(4004, "Invalid session code")
        return

    session.websocket = websocket
    logger.info("WebSocket connected for session %s", code)

    # Send current state
    await websocket.send_text(json.dumps(status_message(session.state.value)))

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send_text(json.dumps(pong_message()))

            elif msg_type in ("screenshot_response", "action_result"):
                # Route to the session's computer use agent
                if session.computer_use_agent:
                    await session.computer_use_agent.handle_ws_message(msg)

    except (WebSocketDisconnect, asyncio.TimeoutError):
        logger.info("WebSocket disconnected for session %s", code)
    except Exception:
        logger.exception("WebSocket error for session %s", code)
    finally:
        if session.websocket is websocket:
            session.websocket = None
