from pydantic import BaseModel
from .events import AgentEvent
from .state import AgentState

class StateTransitionRequest(BaseModel):
    idempotency_key: str
    event: AgentEvent

class TransitionResponse(BaseModel):
    status: str
    message: str
    current_state: AgentState

class RollbackRequest(BaseModel):
    session_id: str
    target_version: int