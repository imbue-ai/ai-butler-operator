"""Register the 4 PhoneBrowserUse tools with VAPI and update the assistant."""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")
SERVER_URL = os.getenv("VAPI_SERVER_URL", "")  # Your ngrok or public URL

if not VAPI_API_KEY or not SERVER_URL:
    print("Set VAPI_API_KEY and VAPI_SERVER_URL in your .env file")
    print("  VAPI_API_KEY=your-vapi-api-key")
    print("  VAPI_SERVER_URL=https://your-ngrok-url.ngrok-free.dev")
    print("  VAPI_ASSISTANT_ID=your-assistant-id  (optional, to auto-attach tools)")
    sys.exit(1)

WEBHOOK_URL = f"{SERVER_URL.rstrip('/')}/api/vapi/webhook"

HEADERS = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "validate_code",
            "description": "Validate the user's 6-digit extension code to start their browser session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The 6-digit code shown on the user's screen",
                    }
                },
                "required": ["code"],
            },
        },
        "server": {"url": WEBHOOK_URL, "timeoutSeconds": 30},
    },
    {
        "type": "function",
        "function": {
            "name": "execute_browser_action",
            "description": "Execute a browser action from the user's natural language instruction, like searching, clicking, or filling forms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "The user's instruction for what to do in the browser",
                    }
                },
                "required": ["instruction"],
            },
        },
        "server": {"url": WEBHOOK_URL, "timeoutSeconds": 60},
    },
    {
        "type": "function",
        "function": {
            "name": "describe_current_page",
            "description": "Describe what is currently visible on the browser screen.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
        "server": {"url": WEBHOOK_URL, "timeoutSeconds": 30},
    },
    {
        "type": "function",
        "function": {
            "name": "go_to_website",
            "description": "Navigate the browser to a specific website URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The website URL to navigate to",
                    }
                },
                "required": ["url"],
            },
        },
        "server": {"url": WEBHOOK_URL, "timeoutSeconds": 30},
    },
]

SYSTEM_PROMPT = """You are a friendly assistant helping elderly users browse the internet via phone.

1. First, ask the user for their 6-digit code shown on their screen. They can read it aloud or type it on their phone's keypad.
2. Use the validate_code tool to verify it. Repeat the code back for confirmation.
3. Once connected, listen to what they want to do and use the appropriate tool.
4. After each action, speak the result clearly and slowly.
5. Use simple, plain language. Be patient and encouraging.
6. If they say a website name, use go_to_website. For anything else (searching, clicking, filling forms), use execute_browser_action.
7. If they ask "what's on the screen", use describe_current_page."""


def get_existing_tools() -> dict[str, str]:
    """Fetch all existing tools and return a mapping of function name -> tool id."""
    resp = requests.get("https://api.vapi.ai/tool", headers=HEADERS)
    if resp.status_code != 200:
        print(f"  Warning: could not list existing tools: {resp.status_code}")
        return {}
    existing: dict[str, str] = {}
    for tool in resp.json():
        func = tool.get("function", {})
        name = func.get("name")
        if name:
            existing[name] = tool["id"]
    return existing


def sync_tools() -> list[str]:
    """Create or update tools so we don't accumulate duplicates."""
    existing = get_existing_tools()
    tool_ids = []
    for tool_def in TOOLS:
        name = tool_def["function"]["name"]
        existing_id = existing.get(name)

        if existing_id:
            # Update the existing tool in place (PATCH rejects the "type" field)
            patch_body = {k: v for k, v in tool_def.items() if k != "type"}
            resp = requests.patch(
                f"https://api.vapi.ai/tool/{existing_id}",
                headers=HEADERS,
                json=patch_body,
            )
            if resp.status_code == 200:
                tool_ids.append(existing_id)
                print(f"  Updated tool: {name} -> {existing_id}")
            else:
                print(f"  FAILED to update {name}: {resp.status_code} {resp.text}")
        else:
            # Create a new tool
            resp = requests.post(
                "https://api.vapi.ai/tool",
                headers=HEADERS,
                json=tool_def,
            )
            if resp.status_code == 201:
                tool = resp.json()
                tool_ids.append(tool["id"])
                print(f"  Created tool: {name} -> {tool['id']}")
            else:
                print(f"  FAILED to create {name}: {resp.status_code} {resp.text}")

    return tool_ids


def update_assistant(tool_ids: list[str]) -> None:
    if not VAPI_ASSISTANT_ID:
        print("\nNo VAPI_ASSISTANT_ID set. Add these tool IDs to your assistant manually:")
        for tid in tool_ids:
            print(f"  {tid}")
        return

    resp = requests.patch(
        f"https://api.vapi.ai/assistant/{VAPI_ASSISTANT_ID}",
        headers=HEADERS,
        json={
            "serverUrl": WEBHOOK_URL,
            "model": {
                "provider": "openai",
                "model": "gpt-4.1",
                "toolIds": tool_ids,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    }
                ],
            },
            "firstMessage": "Hello! Welcome to Phone Browser Use. Please enter your 6-digit code on your phone's keypad, or read it aloud to me.",
            "silenceTimeoutSeconds": 600,
            "keypadInputPlan": {
                "enabled": True,
                "timeoutSeconds": 0,
                "delimiters": ["#"],
            },
        },
    )
    if resp.status_code == 200:
        print(f"\nAssistant {VAPI_ASSISTANT_ID} updated with tools and system prompt.")
    else:
        print(f"\nFAILED to update assistant: {resp.status_code} {resp.text}")
        print("You may need to add the tool IDs manually in the VAPI dashboard.")


if __name__ == "__main__":
    print(f"Webhook URL: {WEBHOOK_URL}\n")
    print("Syncing tools...")
    tool_ids = sync_tools()

    if tool_ids:
        print(f"\n{len(tool_ids)} tools ready.")
        update_assistant(tool_ids)
    else:
        print("\nNo tools were created.")
