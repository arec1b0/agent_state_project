import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException
from src.agent_session.core.exactly_once import ExactlyOnceGuard

@pytest.mark.asyncio
async def test_exactly_once_success(mock_kv_store: AsyncMock) -> None:
    mock_kv_store.lock_idempotency_key.return_value = True
    guard = ExactlyOnceGuard(mock_kv_store)
    
    # Should not raise an exception
    await guard.check_and_lock("unique-key-123")
    mock_kv_store.lock_idempotency_key.assert_called_once_with("unique-key-123")

@pytest.mark.asyncio
async def test_exactly_once_duplicate(mock_kv_store: AsyncMock) -> None:
    mock_kv_store.lock_idempotency_key.return_value = False
    guard = ExactlyOnceGuard(mock_kv_store)
    
    with pytest.raises(HTTPException) as exc:
        await guard.check_and_lock("duplicate-key-123")
    
    assert exc.value.status_code == 409