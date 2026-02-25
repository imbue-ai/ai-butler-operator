# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

PhoneBrowserUse is a voice-controlled remote browser automation system. Users call a phone number (via VAPI), provide a 6-digit session code from the Chrome extension, and control a cloud browser through natural language voice commands. The browser runs on browser-use's cloud infrastructure and is displayed via a live viewer iframe in the extension overlay.

## Commands

```bash
# Run the backend server
.venv/bin/python -m app.main

# Run tests
.venv/bin/pytest
.venv/bin/pytest tests/test_session_manager.py -vxs   # single test file

# Build the Chrome extension
cd ../extension && npm run build    # production
cd ../extension && npm run dev      # watch mode

# Utility scripts
.venv/bin/python test_profile_browser.py --url https://mail.google.com  # open cloud browser with profile (no phone call needed)
.venv/bin/python clear_profile.py          # reset cookies only
.venv/bin/python clear_profile.py --full   # simulate new user
```

## Architecture

### Session Flow

1. **Extension popup** creates a session via `POST /api/session/create` → gets a 6-digit code and phone number
2. Extension opens an overlay iframe (viewer) and connects via **WebSocket** (`/ws/{code}`)
3. User **calls the VAPI phone number** and reads the code → VAPI sends `validate_code` tool call to `/api/vapi/webhook`
4. Backend starts a **cloud browser** (browser-use) with the user's persistent profile and sends the `live_url` over WebSocket
5. User gives voice commands → VAPI sends `execute_browser_action` → backend's persistent `Agent` executes via browser-use
6. On hangup or overlay close → cloud browser is stopped via API (saving cookies to profile)

### Backend (`app/`)

- **`main.py`** — FastAPI app with lifespan. Injects `SessionManager` into all routers. Runs a cleanup loop every 60s.
- **`routers/vapi_webhook.py`** — VAPI webhook handler. Dispatches tool calls: `validate_code`, `execute_browser_action`, `describe_current_page`, `go_to_website`.
- **`routers/extension_api.py`** — REST endpoints for session create/status/end.
- **`routers/websocket_router.py`** — WebSocket endpoint (`/ws/{code}`) for real-time extension communication.
- **`services/browser_service.py`** — Core service. Manages cloud `BrowserSession`, persistent `Agent` (retains context across calls via `add_new_task()`), and page description via Claude vision.
- **`services/session_manager.py`** — Session lifecycle: create → activate (when VAPI call validates code) → end. Handles expiry/cleanup.
- **`services/screenshot_streamer.py`** — WebSocket message helpers: `send_live_url()`, `send_status()`, `send_session_ended()`.
- **`models/session.py`** — Session dataclass with state machine (WAITING_FOR_CALL → ACTIVE → ENDED).
- **`config.py`** — Pydantic Settings loaded from `.env`.

### Extension (`../extension/src/`)

Webpack + TypeScript, Manifest V3. Four entry points:

- **`popup/popup.ts`** — Creates session, gets profile ID from `chrome.storage.local`, injects content script.
- **`content.ts`** — Injects overlay iframe onto the current page with scroll isolation.
- **`viewer/viewer.ts`** — Main UI: shows code/phone, connects WebSocket, loads live browser URL into iframe, handles cleanup.
- **`shared/api.ts`** — REST client (`createSession`, `endSession`). **`websocket.ts`** — Auto-reconnecting WebSocket with ping/pong. **`profile.ts`** — Persistent UUID in `chrome.storage.local`.

### Cloud Browser Profiles

Extension generates a local UUID → backend maps it to a browser-use cloud profile via `POST /api/v2/profiles` → mapping persisted in `cloud_profiles.json`. Cookies survive across sessions when the cloud browser is properly stopped via the API.

## Key Workarounds

**browser-use SDK serialization bug**: The SDK serializes `profile_id` (snake_case) but the cloud API expects `profileId` (camelCase). A monkey-patch on `CreateBrowserRequest.model_dump` in `browser_service.py` remaps field names. Without this, profiles silently don't attach.

**`keep_alive=True` skips cloud stop**: `BrowserSession.stop()` with `keep_alive=True` never calls `stop_browser()` on the cloud API, so cookies don't save. `BrowserService.close()` calls the stop API directly via httpx before `session.stop()`.

**Cloud stop response validation**: The stop API returns null for `liveUrl`/`cdpUrl`, which fails `CloudBrowserResponse` Pydantic validation. We call the API directly with httpx instead of `cloud_client.stop_browser()`.

## Environment Variables (`.env`)

Required: `ANTHROPIC_API_KEY`, `BROWSER_USE_API_KEY`, `VAPI_PHONE_NUMBER`
Optional: `VAPI_API_KEY`, `VAPI_ASSISTANT_ID`, `VAPI_SERVER_URL`, `HOST` (default 0.0.0.0), `PORT` (default 8000), `CORS_ORIGINS`, `CODE_EXPIRY_MINUTES` (10), `SESSION_TIMEOUT_MINUTES` (30)
