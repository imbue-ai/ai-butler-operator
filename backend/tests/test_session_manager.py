import pytest

from app.models.session import SessionState
from app.services.session_manager import SessionManager


def test_create_session(session_manager: SessionManager):
    session = session_manager.create_session()
    assert len(session.code) == 6
    assert session.state == SessionState.WAITING_FOR_CALL


def test_get_session(session_manager: SessionManager):
    session = session_manager.create_session()
    found = session_manager.get_session(session.code)
    assert found is session


def test_get_session_not_found(session_manager: SessionManager):
    assert session_manager.get_session("999999") is None


def test_activate_session(session_manager: SessionManager):
    session = session_manager.create_session()
    activated = session_manager.activate_session(session.code, "call-123")
    assert activated is not None
    assert activated.state == SessionState.ACTIVE
    assert activated.vapi_call_id == "call-123"


def test_activate_invalid_code(session_manager: SessionManager):
    result = session_manager.activate_session("999999", "call-123")
    assert result is None


def test_activate_already_active(session_manager: SessionManager):
    session = session_manager.create_session()
    session_manager.activate_session(session.code, "call-1")
    result = session_manager.activate_session(session.code, "call-2")
    assert result is None


@pytest.mark.asyncio
async def test_end_session(session_manager: SessionManager):
    session = session_manager.create_session()
    code = session.code
    await session_manager.end_session(code)
    assert session_manager.get_session(code) is None


@pytest.mark.asyncio
async def test_end_nonexistent_session(session_manager: SessionManager):
    await session_manager.end_session("999999")  # Should not raise


def test_active_count(session_manager: SessionManager):
    assert session_manager.active_count == 0
    session_manager.create_session()
    session_manager.create_session()
    assert session_manager.active_count == 2
