import httpx
import datetime
import uuid
from typing import Dict, Any, Optional

class AgentStateClient:
    """
    Async SDK for the Agent Session State Manager.
    Decouples the LLM framework orchestration from the infrastructure layer.
    """
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def get_state(self, session_id: str) -> Dict[str, Any]:
        """Return the current AgentState for a session as a dict."""
        response = await self.client.get(f"/session/{session_id}")
        response.raise_for_status()
        return response.json()

    async def transition_state(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
        previous_version: int,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Apply one event to a session.

        `payload` is merged into the session context server-side.
        `previous_version` must match the current state version (OCC), and
        `idempotency_key` (defaults to a fresh UUID) guarantees exactly-once
        application — pass a stable key when retrying the same logical action.

        Raises:
            RuntimeError: on any non-200 response, including OCC conflicts
                (400) and duplicate idempotency keys (409).
        """
        event_id = str(uuid.uuid4())
        key = idempotency_key or event_id
        
        # Format matching the Pydantic datetime parser requirements
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        
        payload_data = {
            "idempotency_key": key,
            "event": {
                "event_id": event_id,
                "session_id": session_id,
                "event_type": event_type,
                "payload": payload,
                "timestamp": timestamp,
                "idempotency_key": key,
                "previous_version": previous_version
            }
        }
        
        response = await self.client.post("/session/transition", json=payload_data)
        
        if response.status_code != 200:
            raise RuntimeError(f"State transition failed with status {response.status_code}: {response.text}")
            
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()