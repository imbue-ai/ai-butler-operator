from __future__ import annotations

import asyncio
import json
import logging

from starlette.websockets import WebSocket, WebSocketState

from app.config import settings

logger = logging.getLogger(__name__)


async def stream_screenshots(
    browser_service,
    websocket: WebSocket,
    session_code: str,
) -> None:
    """Continuously capture screenshots and send them over WebSocket.

    Runs until cancelled or the WebSocket disconnects.
    """
    interval = 1.0 / settings.screenshot_fps

    while True:
        try:
            if websocket.client_state != WebSocketState.CONNECTED:
                logger.info("WebSocket disconnected for session %s", session_code)
                break

            screenshot_b64 = await browser_service.take_screenshot()

            message = json.dumps({
                "type": "screenshot",
                "data": screenshot_b64,
            })
            await websocket.send_text(message)

        except asyncio.CancelledError:
            logger.info("Screenshot streaming cancelled for session %s", session_code)
            raise
        except Exception:
            logger.exception(
                "Error in screenshot stream for session %s", session_code
            )
            await asyncio.sleep(1)
            continue

        await asyncio.sleep(interval)


async def send_status(websocket: WebSocket, status: str, detail: str = "") -> None:
    """Send a status message over the WebSocket."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    message = json.dumps({
        "type": "status",
        "status": status,
        "detail": detail,
    })
    await websocket.send_text(message)


async def send_session_ended(websocket: WebSocket) -> None:
    """Notify the extension that the session has ended."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    message = json.dumps({"type": "session_ended"})
    await websocket.send_text(message)
