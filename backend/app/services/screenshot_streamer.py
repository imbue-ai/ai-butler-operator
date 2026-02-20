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
    logger.info("Screenshot streaming started for session %s (%.1f fps)", session_code, settings.screenshot_fps)
    frame_count = 0

    while True:
        try:
            if websocket.client_state != WebSocketState.CONNECTED:
                logger.info("WebSocket disconnected for session %s", session_code)
                break

            screenshot_b64 = await asyncio.wait_for(
                browser_service.take_screenshot(), timeout=10
            )

            message = json.dumps({
                "type": "screenshot",
                "data": screenshot_b64,
            })
            await websocket.send_text(message)
            frame_count += 1
            if frame_count == 1:
                logger.info("First screenshot sent for session %s", session_code)

        except asyncio.CancelledError:
            logger.info("Screenshot streaming cancelled for session %s (%d frames sent)", session_code, frame_count)
            raise
        except asyncio.TimeoutError:
            logger.warning("Screenshot timed out for session %s, retrying", session_code)
            await asyncio.sleep(1)
            continue
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
