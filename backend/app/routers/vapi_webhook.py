from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request

from app.models.ws_messages import session_ended_message, status_message
from app.services.computer_use_agent import ComputerUseAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vapi", tags=["vapi"])

# session_manager is injected at startup from main.py
session_manager = None


@router.post("/webhook")
async def vapi_webhook(request: Request):
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type", "")

    if msg_type == "tool-calls":
        return await _handle_tool_calls(message)
    elif msg_type == "end-of-call-report":
        return await _handle_end_of_call(message)

    return {"results": []}


async def _handle_tool_calls(message: dict) -> dict:
    tool_calls = message.get("toolCallList", [])
    results = []

    for tc in tool_calls:
        tool_call_id = tc.get("id", "")
        function = tc.get("function", {})
        name = function.get("name", "")
        args = function.get("arguments", {})

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        logger.info("VAPI tool call: %s(%s)", name, json.dumps(args, default=str))

        try:
            result = await _dispatch_tool(name, args, message)
            logger.info("VAPI tool result [%s]: %s", name, result[:200] if result else "(empty)")
            results.append({
                "toolCallId": tool_call_id,
                "result": result,
            })
        except Exception as e:
            logger.exception("Tool call error: %s", name)
            results.append({
                "toolCallId": tool_call_id,
                "error": str(e),
            })

    return {"results": results}


async def _dispatch_tool(name: str, args: dict, message: dict) -> str:
    call_id = message.get("call", {}).get("id", "")
    if name == "validate_code":
        return await _validate_code(args, message)
    elif name == "execute_browser_action":
        return await _execute_browser_action(args, call_id)
    elif name == "describe_current_page":
        return await _describe_current_page(args, call_id)
    elif name == "go_to_website":
        return await _go_to_website(args, call_id)
    else:
        return f"Unknown tool: {name}"


async def _validate_code(args: dict, message: dict) -> str:
    code = args.get("code", "").strip()
    if not code or len(code) != 6 or not code.isdigit():
        return "That doesn't seem like a valid code. Please ask the user for their 6-digit code shown on their screen."

    call_id = message.get("call", {}).get("id", "unknown")
    session = session_manager.activate_session(code, call_id)

    if session is None:
        return "That code is not valid or has already been used. Please ask the user to check their screen and try again."

    # Send active status to extension via WebSocket
    if session.websocket:
        await session.websocket.send_text(
            json.dumps(status_message("active"))
        )

    # Create a ComputerUseAgent for this session
    if session.websocket:
        agent = ComputerUseAgent(session.websocket, code)
        session.computer_use_agent = agent
        logger.info("ComputerUseAgent created for session %s", code)
    else:
        logger.warning("No WebSocket connected for session %s", code)

    return (
        "Code verified successfully! I can now see the user's browser. "
        "What would you like me to help you find or do on the internet?"
    )


async def _execute_browser_action(args: dict, call_id: str) -> str:
    instruction = args.get("instruction", "").strip()
    if not instruction:
        return "I didn't catch what you'd like me to do. Could you say that again?"

    session = session_manager.get_session_by_call_id(call_id)
    if not session or not session.computer_use_agent:
        return "I'm sorry, but I don't have an active browser session."

    if not session.websocket:
        return "The browser extension is disconnected. Please check the extension."

    session.touch()

    # Ensure agent has current websocket reference
    session.computer_use_agent._ws = session.websocket

    try:
        result = await session.computer_use_agent.execute(instruction)
        return result
    except Exception as e:
        logger.exception("Browser action failed: %s", instruction)
        return "I had trouble doing that. Could you try asking in a different way?"


async def _describe_current_page(args: dict, call_id: str) -> str:
    session = session_manager.get_session_by_call_id(call_id)
    if not session or not session.computer_use_agent:
        return "I don't have an active browser session right now."

    if not session.websocket:
        return "The browser extension is disconnected."

    session.touch()
    session.computer_use_agent._ws = session.websocket

    try:
        # Take a screenshot and describe it using Claude vision
        import anthropic
        from app.config import settings

        b64_data, _, _, _ = await session.computer_use_agent.request_screenshot()

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this web page in 2-3 simple sentences "
                                "for an elderly person who is listening over the phone. "
                                "Focus on what's visible and any key information. "
                                "Use plain, easy-to-understand language."
                            ),
                        },
                    ],
                }
            ],
        )
        return response.content[0].text
    except Exception:
        logger.exception("Page description failed")
        return "I'm having trouble seeing the page right now."


async def _go_to_website(args: dict, call_id: str) -> str:
    url = args.get("url", "").strip()
    if not url:
        return "I didn't catch the website address. Could you say it again?"

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    session = session_manager.get_session_by_call_id(call_id)
    if not session or not session.computer_use_agent:
        return "I don't have an active browser session right now."

    if not session.websocket:
        return "The browser extension is disconnected."

    session.touch()
    session.computer_use_agent._ws = session.websocket

    try:
        # Navigate the tab directly via chrome.tabs.update
        success = await session.computer_use_agent.navigate(url)
        if not success:
            return "I had trouble navigating to that website."

        # Describe the page after navigation
        import anthropic
        from app.config import settings

        b64_data, _, _, _ = await session.computer_use_agent.request_screenshot()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this web page in 2-3 simple sentences "
                                "for someone listening over the phone. "
                                "Focus on what's visible and any key information."
                            ),
                        },
                    ],
                }
            ],
        )
        return response.content[0].text
    except Exception as e:
        logger.exception("Navigation failed: %s", url)
        return "I had trouble going to that website. Could you check the address?"


async def _handle_end_of_call(message: dict) -> dict:
    call_id = message.get("call", {}).get("id", "")
    logger.info("End-of-call received for call_id: %s", call_id)

    found = False
    for code, session in list(session_manager._sessions.items()):
        if session.vapi_call_id == call_id:
            found = True
            if session.websocket:
                await session.websocket.send_text(
                    json.dumps(session_ended_message())
                )
            await session_manager.end_session(code)
            logger.info("Call ended, session %s cleaned up", code)
            break

    if not found:
        logger.warning("No session found for call_id: %s", call_id)

    return {}
