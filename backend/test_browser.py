"""Interactive script to test browser-use actions and measure timing."""

import asyncio
import time

from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, BrowserSession, ChatBrowserUse


async def main():
    llm = ChatBrowserUse(model="bu-2-0")

    print("Starting browser...")
    t = time.time()
    session = BrowserSession(headless=False, keep_alive=True)
    await session.start()
    page = await session.get_current_page()
    await page.goto("https://www.google.com")
    print(f"Browser started in {time.time() - t:.1f}s\n")

    print("Enter instructions (or 'quit' to exit):\n")

    while True:
        instruction = input("> ").strip()
        if not instruction or instruction.lower() in ("quit", "exit", "q"):
            break

        print(f"Running: {instruction}")
        t = time.time()

        try:
            agent = Agent(
                task=instruction,
                llm=llm,
                browser_session=session,
            )
            result = await agent.run()
            elapsed = time.time() - t

            final = result.final_result()
            print(f"\n--- Result ({elapsed:.1f}s) ---")
            print(final or "(no result text)")
            print("---\n")
        except Exception as e:
            elapsed = time.time() - t
            print(f"\n--- Error ({elapsed:.1f}s) ---")
            print(f"{e}\n")

    print("Closing browser...")
    await session.stop()


if __name__ == "__main__":
    asyncio.run(main())
