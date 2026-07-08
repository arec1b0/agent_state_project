from typing import AsyncGenerator
from fastapi import Depends
from ..infrastructure.kv_store import KVStore
from ..infrastructure.event_journal import EventJournal
from ..infrastructure.db_session import get_db_pool
from ..core.exactly_once import ExactlyOnceGuard
from ..core.state_manager import StateManager
from ..core.rollback_engine import RollbackEngine
from ..core.telemetry import AgentTelemetry

def get_telemetry() -> AgentTelemetry:
    return AgentTelemetry()

async def get_kv_store() -> AsyncGenerator[KVStore, None]:
    store = KVStore()
    try:
        yield store
    finally:
        await store.close()

def get_event_journal() -> EventJournal:
    pool = get_db_pool()
    return EventJournal(pool=pool)

def get_exactly_once_guard(
    kv_store: KVStore = Depends(get_kv_store)
) -> ExactlyOnceGuard:
    return ExactlyOnceGuard(kv_store=kv_store)

def get_state_manager(
    kv_store: KVStore = Depends(get_kv_store),
    journal: EventJournal = Depends(get_event_journal),
    telemetry: AgentTelemetry = Depends(get_telemetry)
) -> StateManager:
    return StateManager(kv_store=kv_store, journal=journal, telemetry=telemetry)

def get_rollback_engine(
    kv_store: KVStore = Depends(get_kv_store),
    journal: EventJournal = Depends(get_event_journal),
    telemetry: AgentTelemetry = Depends(get_telemetry)
) -> RollbackEngine:
    return RollbackEngine(journal=journal, kv_store=kv_store, telemetry=telemetry)