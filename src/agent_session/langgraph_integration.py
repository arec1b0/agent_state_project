import base64
from typing import Optional, AsyncIterator, Tuple, Any, Sequence, Dict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from .client import AgentStateClient


class APIStateCheckpointer(BaseCheckpointSaver):
    """
    Delegates LangGraph state storage to the Agent State API.

    LangGraph checkpoints contain Python objects (HumanMessage, AIMessage,
    ToolMessage, etc.) that cannot be serialized directly to JSON.
    JsonPlusSerializer converts them into a JSON-compatible representation
    before sending them over HTTP.
    """

    def __init__(self, client: AgentStateClient):
        super().__init__()
        self.client = client
        self.serde = JsonPlusSerializer()

    def _dumps_json_safe(self, obj: Any) -> list:
        # dumps_typed returns (type, bytes); bytes cannot travel as JSON,
        # so the blob is base64-encoded for the HTTP payload.
        type_, blob = self.serde.dumps_typed(obj)
        return [type_, base64.b64encode(blob).decode("ascii")]

    def _loads_json_safe(self, value: Sequence[str]) -> Any:
        type_, blob_b64 = value
        return self.serde.loads_typed((type_, base64.b64decode(blob_b64)))

    # ------------------------------------------------------------------
    # Async methods
    # ------------------------------------------------------------------

    async def aget_tuple(
        self,
        config: RunnableConfig,
    ) -> Optional[CheckpointTuple]:

        session_id = config["configurable"]["thread_id"]

        try:
            state_data = await self.client.get_state(session_id)
        except Exception:
            return None

        context = state_data.get("context", {})

        if "langgraph_checkpoint" not in context:
            return None

        checkpoint = self._loads_json_safe(context["langgraph_checkpoint"])

        if "langgraph_metadata" in context:
            metadata = self._loads_json_safe(context["langgraph_metadata"])
        else:
            metadata = {}

        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=None,
            pending_writes=[],
        )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:

        session_id = config["configurable"]["thread_id"]

        current_state = await self.client.get_state(session_id)
        previous_version = current_state.get("version", 0)

        payload = {
            "langgraph_checkpoint": self._dumps_json_safe(checkpoint),
            "langgraph_metadata": self._dumps_json_safe(metadata),
        }

        await self.client.transition_state(
            session_id=session_id,
            event_type="LANGGRAPH_CHECKPOINT",
            payload=payload,
            previous_version=previous_version,
            idempotency_key=checkpoint["id"],
        )

        return {
            "configurable": {
                "thread_id": session_id,
                "checkpoint_ns": config["configurable"].get(
                    "checkpoint_ns",
                    "",
                ),
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        pass

    async def alist(
        self,
        config: RunnableConfig,
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        if False:
            yield

    # ------------------------------------------------------------------
    # Sync API (unsupported)
    # ------------------------------------------------------------------

    def get_tuple(self, config: RunnableConfig):
        raise NotImplementedError(
            "Use async execution (ainvoke/astream)."
        )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ):
        raise NotImplementedError(
            "Use async execution (ainvoke/astream)."
        )

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ):
        raise NotImplementedError(
            "Use async execution (ainvoke/astream)."
        )

    def list(
        self,
        config: RunnableConfig,
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ):
        raise NotImplementedError(
            "Use async execution (ainvoke/astream)."
        )