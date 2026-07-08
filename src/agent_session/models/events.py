from pydantic import BaseModel, Field
from typing import Dict, Any
from datetime import datetime, timezone

class AgentEvent(BaseModel):
    event_id: str
    session_id: str
    event_type: str = Field(
        description="Type of action, e.g., 'TOOL_CALL', 'LLM_RESPONSE', 'USER_PROMPT'."
    )
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    idempotency_key: str = Field(
        description="Crucial for exactly-once processing guarantees."
    )
    previous_version: int = Field(
        description="The state version before this event was applied. Required for deterministic rollback."
    )