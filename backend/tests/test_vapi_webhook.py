from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, session_manager


@pytest.fixture(autouse=True)
def _clean_sessions():
    """Ensure clean state between tests."""
    session_manager._sessions.clear()
    session_manager._code_generator._active_codes.clear()
    yield
    session_manager._sessions.clear()
    session_manager._code_generator._active_codes.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_session(client: AsyncClient):
    resp = await client.post("/api/session/create")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["code"]) == 6
    assert "phone_number" in data


@pytest.mark.asyncio
async def test_session_status(client: AsyncClient):
    create_resp = await client.post("/api/session/create")
    code = create_resp.json()["code"]

    resp = await client.get(f"/api/session/{code}/status")
    assert resp.status_code == 200
    assert resp.json()["state"] == "waiting_for_call"


@pytest.mark.asyncio
async def test_session_status_not_found(client: AsyncClient):
    resp = await client.get("/api/session/999999/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_validate_code_success(client: AsyncClient):
    create_resp = await client.post("/api/session/create")
    code = create_resp.json()["code"]

    webhook_payload = {
        "message": {
            "type": "tool-calls",
            "call": {"id": "test-call-1"},
            "toolCallList": [
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {
                        "name": "validate_code",
                        "arguments": {"code": code},
                    },
                }
            ],
        }
    }

    with patch(
        "app.routers.vapi_webhook.BrowserService"
    ) as MockBrowserService:
        mock_instance = AsyncMock()
        MockBrowserService.return_value = mock_instance

        resp = await client.post("/api/vapi/webhook", json=webhook_payload)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert "verified" in data["results"][0]["result"].lower()


@pytest.mark.asyncio
async def test_validate_code_invalid(client: AsyncClient):
    webhook_payload = {
        "message": {
            "type": "tool-calls",
            "call": {"id": "test-call-2"},
            "toolCallList": [
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {
                        "name": "validate_code",
                        "arguments": {"code": "000000"},
                    },
                }
            ],
        }
    }

    resp = await client.post("/api/vapi/webhook", json=webhook_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "not valid" in data["results"][0]["result"].lower()


@pytest.mark.asyncio
async def test_end_of_call(client: AsyncClient):
    webhook_payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "some-call-id"},
        }
    }

    resp = await client.post("/api/vapi/webhook", json=webhook_payload)
    assert resp.status_code == 200
