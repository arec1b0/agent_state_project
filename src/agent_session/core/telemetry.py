import os
import asyncio
from functools import partial
from mlflow.client import MlflowClient
from ..models.events import AgentEvent

class AgentTelemetry:
    def __init__(self) -> None:
        self.client = MlflowClient(tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
        self.exp_name = "agent_sessions"
        
        experiment = self.client.get_experiment_by_name(self.exp_name)
        self.exp_id = experiment.experiment_id if experiment else self.client.create_experiment(self.exp_name)

    async def _get_or_create_run(self, session_id: str) -> str:
        loop = asyncio.get_running_loop()
        query = f"tags.session_id = '{session_id}'"
        
        runs = await loop.run_in_executor(
            None, partial(self.client.search_runs, experiment_ids=[self.exp_id], filter_string=query)
        )
        
        if runs:
            return runs[0].info.run_id
            
        run = await loop.run_in_executor(
            None, partial(self.client.create_run, experiment_id=self.exp_id, tags={"session_id": session_id})
        )
        return run.info.run_id

    async def log_transition(self, event: AgentEvent, latency_ms: float) -> None:
        run_id = await self._get_or_create_run(event.session_id)
        new_version = event.previous_version + 1
        loop = asyncio.get_running_loop()
        
        await loop.run_in_executor(None, partial(
            self.client.log_metric, run_id, f"{event.event_type}_latency_ms", latency_ms, step=new_version
        ))
        await loop.run_in_executor(None, partial(
            self.client.log_metric, run_id, "state_version", new_version, step=new_version
        ))
        await loop.run_in_executor(None, partial(
            self.client.log_dict, run_id, event.payload, f"events/v{new_version}_{event.event_id}.json"
        ))

    async def log_rollback(self, session_id: str, target_version: int) -> None:
        run_id = await self._get_or_create_run(session_id)
        loop = asyncio.get_running_loop()
        
        await loop.run_in_executor(None, partial(
            self.client.log_metric, run_id, "rollback_triggered", 1.0, step=target_version
        ))