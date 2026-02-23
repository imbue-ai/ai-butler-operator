from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    WAITING_FOR_CALL = "waiting_for_call"
    ACTIVE = "active"
    ENDED = "ended"


@dataclass
class Session:
    code: str
    state: SessionState = SessionState.WAITING_FOR_CALL
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    # Set when VAPI call connects
    vapi_call_id: str | None = None

    # WebSocket connection for the extension
    websocket: Any = None

    # Computer use agent instance (set when session is activated)
    computer_use_agent: Any = None

    def touch(self) -> None:
        self.last_activity = time.time()
