from pydantic import BaseModel, Field
from typing import Dict, Any

class AgentState(BaseModel):
    session_id: str
    version: int = Field(
        default=0, 
        description="Used for optimistic concurrency control (OCC) to prevent race conditions."
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, 
        description="The actual state payload of the LLM/Agent."
    )
    status: str = Field(
        default="active", 
        description="Session status: active, completed, or suspended."
    )