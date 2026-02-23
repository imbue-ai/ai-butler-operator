from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.api_models import SessionCreateResponse, SessionStatusResponse

router = APIRouter(prefix="/api/session", tags=["session"])

# session_manager is injected at startup from main.py
session_manager = None


@router.post("/create", response_model=SessionCreateResponse)
async def create_session():
    session = session_manager.create_session()
    return SessionCreateResponse(
        code=session.code,
        phone_number=settings.vapi_phone_number,
    )


@router.get("/{code}/status", response_model=SessionStatusResponse)
async def get_session_status(code: str):
    session = session_manager.get_session(code)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionStatusResponse(
        code=session.code,
        state=session.state.value,
    )
