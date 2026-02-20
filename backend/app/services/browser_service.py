from __future__ import annotations

import asyncio
import base64
import logging

import anthropic
from browser_use import Agent, BrowserSession, ChatBrowserUse

from app.config import settings

logger = logging.getLogger(__name__)


class BrowserService:
    """Wraps browser-use library for browser automation with BU 2.0."""

    def __init__(self) -> None:
        self._session: BrowserSession | None = None
        self._llm = ChatBrowserUse(model="bu-2-0")
        self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._agent_task: asyncio.Task | None = None
        self._stopped = False

    async def start_browser(self, url: str = "https://www.google.com") -> None:
        self._session = BrowserSession(headless=True, keep_alive=True)
        await self._session.start()
        # Open the requested page
        page = await self._session.get_current_page()
        await page.goto(url)
        logger.info("Browser started and navigated to %s", url)

    async def execute_action(self, instruction: str) -> str:
        """Run a browser-use agent with a natural language instruction.
        Returns the agent's own description of what happened."""
        if self._stopped:
            raise RuntimeError("Browser service has been stopped")
        if not self._session:
            raise RuntimeError("Browser not started")

        agent = Agent(
            task=instruction,
            llm=self._llm,
            browser_session=self._session,
        )
        self._agent_task = asyncio.create_task(agent.run())
        try:
            result = await self._agent_task
        except asyncio.CancelledError:
            logger.info("Agent task was cancelled (session ended)")
            raise RuntimeError("Browser session ended")
        finally:
            self._agent_task = None

        if self._stopped:
            raise RuntimeError("Browser service has been stopped")

        # Extract the agent's final result text
        final = result.final_result()
        if final:
            return final

        # Fallback: use vision to describe the page
        return await self.describe_page()

    async def navigate_to(self, url: str) -> str:
        """Navigate directly to a URL. Returns page description."""
        if not self._session:
            raise RuntimeError("Browser not started")

        page = await self._session.get_current_page()
        await page.goto(url)
        logger.info("Navigated to %s", url)

        return await self.describe_page()

    async def take_screenshot(self) -> str:
        """Take a screenshot and return base64-encoded JPEG."""
        if not self._session:
            raise RuntimeError("Browser not started")

        screenshot_bytes = await self._session.take_screenshot(
            format="jpeg", quality=70
        )
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def describe_page(self) -> str:
        """Use Claude vision to describe the current page in 2-3 simple sentences."""
        screenshot_b64 = await self.take_screenshot()

        response = self._anthropic.messages.create(
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

    async def stop(self) -> None:
        """Signal the service to stop and cancel any running agent task."""
        self._stopped = True
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
            logger.info("Cancelled running agent task")

    async def close(self) -> None:
        await self.stop()
        if self._session:
            # Use kill() for force shutdown — skips storage state saving
            # and other watchdog operations that fail during teardown
            await self._session.kill()
            self._session = None
            logger.info("Browser closed")
