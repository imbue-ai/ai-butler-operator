from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import anthropic
from browserbase import AsyncBrowserbase
from playwright.async_api import async_playwright

from app.config import settings

logger = logging.getLogger(__name__)

# Map Claude computer-use key names → Playwright key names
_KEY_MAP = {
    "Return": "Enter",
    "BackSpace": "Backspace",
    "ctrl": "Control",
    "alt": "Alt",
    "shift": "Shift",
    "super": "Meta",
    "space": " ",
    "Tab": "Tab",
    "Escape": "Escape",
    "Delete": "Delete",
    "Home": "Home",
    "End": "End",
    "Page_Up": "PageUp",
    "Page_Down": "PageDown",
    "Up": "ArrowUp",
    "Down": "ArrowDown",
    "Left": "ArrowLeft",
    "Right": "ArrowRight",
}


def _map_key(name: str) -> str:
    """Translate a single key name from Claude to Playwright."""
    return _KEY_MAP.get(name, name)


def _map_keys(combo: str) -> str:
    """Translate a key combo like 'ctrl+a' → 'Control+a'."""
    return "+".join(_map_key(k) for k in combo.split("+"))


class BrowserService:
    """Uses Claude computer-use API with a remote Browserbase browser."""

    # Viewport that fits within the API's 1568px / 1.15MP constraints
    DISPLAY_W = 1280
    DISPLAY_H = 800

    def __init__(self) -> None:
        self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._bb = AsyncBrowserbase(api_key=settings.browserbase_api_key)
        self._pw: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._live_view_url: str | None = None
        self._browserbase_session_id: str | None = None
        self._stopped = False

    # ── properties ──────────────────────────────────────────────────────

    @property
    def live_view_url(self) -> str | None:
        return self._live_view_url

    @property
    def browserbase_session_id(self) -> str | None:
        return self._browserbase_session_id

    # ── lifecycle ───────────────────────────────────────────────────────

    async def start_browser(self, url: str = "https://www.google.com") -> None:
        """Create a Browserbase session, connect via CDP, and navigate."""
        logger.info("[BROWSER] Creating Browserbase session…")
        bb_session = await self._bb.sessions.create(
            project_id=settings.browserbase_project_id,
        )
        self._browserbase_session_id = bb_session.id
        logger.info("[BROWSER] Session created: %s", bb_session.id)

        # Get the CDP URL and live-view URL
        debug_info = await self._bb.sessions.debug(bb_session.id)
        self._live_view_url = debug_info.debugger_fullscreen_url
        ws_url = debug_info.ws_url
        logger.info("[BROWSER] Live view: %s", self._live_view_url)

        # Connect Playwright over CDP
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.connect_over_cdp(ws_url)

        ctx = self._browser.contexts[0]
        self._page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await self._page.set_viewport_size(
            {"width": self.DISPLAY_W, "height": self.DISPLAY_H}
        )
        logger.info("[BROWSER] Connected via CDP, viewport %dx%d", self.DISPLAY_W, self.DISPLAY_H)

        # Navigate to the starting page
        logger.info("[BROWSER] Navigating to %s", url)
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        logger.info("[BROWSER] Navigation complete")

    async def stop(self) -> None:
        self._stopped = True

    async def close(self) -> None:
        """Disconnect Playwright and release resources."""
        logger.info("[BROWSER] Closing…")
        self._stopped = True
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                logger.debug("Error closing browser connection", exc_info=True)
            self._browser = None
            self._page = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                logger.debug("Error stopping playwright", exc_info=True)
            self._pw = None
        self._live_view_url = None
        logger.info("[BROWSER] Closed")

    # ── public API ──────────────────────────────────────────────────────

    async def execute_action(self, instruction: str) -> str:
        """Run the Claude computer-use agent loop for *instruction*.

        Returns a short, user-friendly description of what happened.
        """
        if self._stopped or not self._page:
            raise RuntimeError("Browser not started or stopped")

        # Start the conversation with a screenshot + the user instruction
        screenshot_b64 = await self._take_screenshot()

        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {"type": "text", "text": instruction},
                ],
            }
        ]

        system_prompt = (
            "You are controlling a web browser to help a user. "
            "Execute the requested action efficiently with as few steps as possible. "
            "After completing the task, briefly describe what happened and what is "
            "now visible on the page in 2-3 simple sentences for someone listening "
            "over the phone. Use plain, easy-to-understand language."
        )

        tools: list[dict] = [
            {
                "type": "computer_20250124",
                "name": "computer",
                "display_width_px": self.DISPLAY_W,
                "display_height_px": self.DISPLAY_H,
            }
        ]

        max_turns = 25
        for turn in range(max_turns):
            if self._stopped:
                return "The browser session was stopped."

            logger.info("[CU] Turn %d – calling Claude…", turn + 1)
            response = self._anthropic.beta.messages.create(
                model=settings.computer_use_model,
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
                betas=["computer-use-2025-01-24"],
            )

            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})

            # Process tool calls
            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("[CU] Tool call: %s → %s", block.name, block.input.get("action"))
                    result = await self._handle_computer_tool(block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            if not tool_results:
                # Claude finished – extract its text reply
                for block in response.content:
                    if hasattr(block, "text"):
                        logger.info("[CU] Done after %d turns", turn + 1)
                        return block.text
                return "Action completed."

            messages.append({"role": "user", "content": tool_results})

        return "I completed the action."

    async def describe_page(self) -> str:
        """Take a screenshot and ask Claude to describe the page."""
        if not self._page:
            raise RuntimeError("Browser not started")

        screenshot_b64 = await self._take_screenshot()
        response = self._anthropic.messages.create(
            model=settings.computer_use_model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
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

    async def navigate_to(self, url: str) -> str:
        """Navigate and return a description."""
        await self.navigate_to_fast(url)
        return await self.describe_page()

    async def navigate_to_fast(self, url: str) -> None:
        """Navigate without describing the page."""
        if not self._page:
            raise RuntimeError("Browser not started")
        logger.info("[BROWSER] Navigating to %s", url)
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        logger.info("[BROWSER] Navigation complete")

    async def take_screenshot(self) -> str:
        """Public helper – returns base64-encoded PNG."""
        return await self._take_screenshot()

    # ── internal helpers ────────────────────────────────────────────────

    async def _take_screenshot(self) -> str:
        screenshot_bytes = await self._page.screenshot(type="png")
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def _handle_computer_tool(self, tool_input: dict) -> Any:
        """Execute a single computer-use action and return the tool result."""
        action = tool_input.get("action", "")

        if action == "screenshot":
            b64 = await self._take_screenshot()
            return [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                }
            ]

        # Execute the browser action
        try:
            await self._dispatch_action(action, tool_input)
        except Exception as e:
            logger.warning("[CU] Action '%s' failed: %s", action, e)
            return f"Error executing {action}: {e}"

        # Brief pause so the page can settle, then return a screenshot
        await asyncio.sleep(0.3)
        b64 = await self._take_screenshot()
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            }
        ]

    async def _dispatch_action(self, action: str, params: dict) -> None:
        """Translate a Claude computer-use action into Playwright calls."""
        page = self._page

        if action == "left_click":
            x, y = params["coordinate"]
            mod = params.get("text")
            if mod:
                await page.keyboard.down(_map_key(mod))
            await page.mouse.click(x, y)
            if mod:
                await page.keyboard.up(_map_key(mod))

        elif action == "right_click":
            x, y = params["coordinate"]
            await page.mouse.click(x, y, button="right")

        elif action == "double_click":
            x, y = params["coordinate"]
            await page.mouse.dblclick(x, y)

        elif action == "triple_click":
            x, y = params["coordinate"]
            await page.mouse.click(x, y, click_count=3)

        elif action == "middle_click":
            x, y = params["coordinate"]
            await page.mouse.click(x, y, button="middle")

        elif action == "mouse_move":
            x, y = params["coordinate"]
            await page.mouse.move(x, y)

        elif action == "type":
            await page.keyboard.type(params["text"])

        elif action == "key":
            combo = _map_keys(params["text"])
            await page.keyboard.press(combo)

        elif action == "scroll":
            x, y = params.get("coordinate", [self.DISPLAY_W // 2, self.DISPLAY_H // 2])
            direction = params.get("scroll_direction", "down")
            amount = params.get("scroll_amount", 3)
            dx, dy = 0, 0
            if direction == "down":
                dy = amount * 100
            elif direction == "up":
                dy = -(amount * 100)
            elif direction == "right":
                dx = amount * 100
            elif direction == "left":
                dx = -(amount * 100)
            mod = params.get("text")
            if mod:
                await page.keyboard.down(_map_key(mod))
            await page.mouse.move(x, y)
            await page.mouse.wheel(dx, dy)
            if mod:
                await page.keyboard.up(_map_key(mod))

        elif action == "left_click_drag":
            sx, sy = params["start_coordinate"]
            ex, ey = params["coordinate"]
            await page.mouse.move(sx, sy)
            await page.mouse.down()
            await page.mouse.move(ex, ey)
            await page.mouse.up()

        elif action == "left_mouse_down":
            await page.mouse.down()

        elif action == "left_mouse_up":
            await page.mouse.up()

        elif action == "hold_key":
            key = _map_key(params["text"])
            duration = params.get("duration", 1)
            await page.keyboard.down(key)
            await asyncio.sleep(duration)
            await page.keyboard.up(key)

        elif action == "wait":
            await asyncio.sleep(params.get("duration", 1))

        else:
            logger.warning("[CU] Unknown action: %s", action)
