from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Depends
import structlog

from ..infrastructure.db_session import init_db_pool, close_db_pool
from ..models.contracts import StateTransitionRequest, TransitionResponse, RollbackRequest
from ..models.state import AgentState
from ..core.exactly_once import ExactlyOnceGuard
from ..core.state_manager import StateManager
from ..core.rollback_engine import RollbackEngine
from ..utils.logging_config import setup_logging
from .exceptions import value_error_handler, runtime_error_handler
from .dependencies import get_exactly_once_guard, get_state_manager, get_rollback_engine

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info("system_startup", message="Initializing database pool")
    await init_db_pool()
    yield
    logger.info("system_shutdown", message="Closing database pool")
    await close_db_pool()

app = FastAPI(
    title="Agent Session State Manager",
    description="State-centric architecture for LLM agent sessions",
    version="0.1.0",
    lifespan=lifespan
)

app.add_exception_handler(ValueError, value_error_handler)
app.add_exception_handler(RuntimeError, runtime_error_handler)

@app.post("/session/transition", response_model=TransitionResponse)
async def transition_state(
    request: StateTransitionRequest,
    guard: ExactlyOnceGuard = Depends(get_exactly_once_guard),
    manager: StateManager = Depends(get_state_manager)
) -> TransitionResponse:
    
    await guard.check_and_lock(request.idempotency_key)
    logger.info("processing_event", session_id=request.event.session_id, event_type=request.event.event_type)
    
    new_state = await manager.apply_event(request.event)
    
    return TransitionResponse(
        status="success",
        message="State transition applied successfully.",
        current_state=new_state
    )

@app.get("/session/{session_id}", response_model=AgentState)
async def get_state(
    session_id: str,
    manager: StateManager = Depends(get_state_manager)
) -> AgentState:
    
    return await manager.get_current_state(session_id)

@app.post("/session/rollback", response_model=AgentState)
async def rollback_state(
    request: RollbackRequest,
    engine: RollbackEngine = Depends(get_rollback_engine)
) -> AgentState:
    
    logger.warning("initiating_rollback", session_id=request.session_id, target_version=request.target_version)
    return await engine.rollback_to_version(request.session_id, request.target_version)