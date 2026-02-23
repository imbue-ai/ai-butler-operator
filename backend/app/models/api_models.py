from pydantic import BaseModel


class SessionCreateResponse(BaseModel):
    code: str
    phone_number: str


class SessionStatusResponse(BaseModel):
    code: str
    state: str


class VapiFunction(BaseModel):
    name: str
    arguments: dict = {}


class VapiToolCall(BaseModel):
    """Represents a single tool call from VAPI."""
    id: str
    type: str = "function"
    function: VapiFunction


class VapiWebhookRequest(BaseModel):
    """Incoming VAPI webhook payload."""
    message: dict
