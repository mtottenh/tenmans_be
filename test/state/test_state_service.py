"""Test suite for StateService business logic"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import json
import uuid
from pydantic import BaseModel
from typing import Optional, Any

from state.service import StateService, StateType, State
from config import Config


class TestModel(BaseModel):
    """Test model for state service tests"""
    id: str
    name: str
    value: int
    metadata: Optional[dict[str, Any]] = None


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.get = AsyncMock()
    redis.delete = AsyncMock()
    redis.exists = AsyncMock()
    redis.expire = AsyncMock()
    redis.scan = AsyncMock()
    redis.pipeline = Mock(return_value=AsyncMock())
    return redis


@pytest.fixture
def state_service(mock_redis):
    """Create StateService with mocked Redis"""
    with patch('redis.asyncio.from_url', return_value=mock_redis):
        service = StateService("redis://localhost:6379")
    return service


@pytest.fixture
def test_state_data():
    """Create test state data"""
    return TestModel(
        id=str(uuid.uuid4()),
        name="test_item",
        value=42,
        metadata={"foo": "bar"}
    )


def test_get_key(state_service):
    """Test key generation"""
    # Execute
    key = state_service._get_key(StateType.AUTH, "test123")
    
    # Assert
    assert key == "state:auth:test123"


def test_get_expiry_time(state_service):
    """Test getting expiry time for different state types"""
    # Test each state type
    assert state_service.get_expiry_time(StateType.AUTH) == timedelta(minutes=5)
    assert state_service.get_expiry_time(StateType.PASSWORD_RESET) == timedelta(hours=24)
    assert state_service.get_expiry_time(StateType.EMAIL_VERIFICATION) == timedelta(hours=48)
    assert state_service.get_expiry_time(StateType.FILE_UPLOAD) == timedelta(minutes=30)
    assert state_service.get_expiry_time(StateType.FILE_UPLOAD_RESULT) == timedelta(minutes=50)
    assert state_service.get_expiry_time(StateType.GENERAL) == timedelta(minutes=15)


@pytest.mark.asyncio
async def test_set_state(state_service, test_state_data):
    """Test setting state data"""
    # Setup
    state_id = str(uuid.uuid4())
    state_type = StateType.GENERAL
    
    # Execute
    await state_service.set_state(
        state_type=state_type,
        state_id=state_id,
        data=test_state_data
    )
    
    # Assert
    state_service.redis.set.assert_called_once()
    call_args = state_service.redis.set.call_args
    
    # Verify key
    assert call_args[0][0] == f"state:{state_type}:{state_id}"
    
    # Verify data serialization
    stored_data = json.loads(call_args[0][1])
    assert stored_data["type"] == state_type
    assert json.loads(stored_data["data"]) == test_state_data.model_dump()
    
    # Verify expiry
    assert call_args[1]["ex"] == state_service.expiry_times[state_type].total_seconds()


@pytest.mark.asyncio
async def test_set_state_with_custom_ttl(state_service, test_state_data):
    """Test setting state with custom TTL"""
    # Setup
    state_id = str(uuid.uuid4())
    state_type = StateType.GENERAL
    custom_ttl = timedelta(hours=1)
    
    # Execute
    await state_service.set_state(
        state_type=state_type,
        state_id=state_id,
        data=test_state_data,
        ttl=custom_ttl
    )
    
    # Assert
    call_args = state_service.redis.set.call_args
    assert call_args[1]["ex"] == custom_ttl.total_seconds()


@pytest.mark.asyncio
async def test_get_state(state_service, test_state_data):
    """Test getting state data"""
    # Setup
    state_id = str(uuid.uuid4())
    state_type = StateType.GENERAL
    
    stored_state = State(
        type=state_type,
        data=test_state_data.model_dump_json(),
        metadata={"created_at": datetime.now().isoformat()}
    )
    
    state_service.redis.get.return_value = stored_state.model_dump_json()
    
    # Execute
    result = await state_service.get_state(
        state_type=state_type,
        state_id=state_id,
        model_class=TestModel
    )
    
    # Assert
    assert isinstance(result, TestModel)
    assert result.id == test_state_data.id
    assert result.name == test_state_data.name
    assert result.value == test_state_data.value


@pytest.mark.asyncio
async def test_get_state_not_found(state_service):
    """Test getting non-existent state"""
    # Setup
    state_service.redis.get.return_value = None
    
    # Execute
    result = await state_service.get_state(
        state_type=StateType.GENERAL,
        state_id="non-existent",
        model_class=TestModel
    )
    
    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_get_state_raw(state_service):
    """Test getting raw state data without model parsing"""
    # Setup
    state_id = str(uuid.uuid4())
    state_type = StateType.GENERAL
    
    state_data = {"foo": "bar", "baz": 123}
    stored_state = State(
        type=state_type,
        data=json.dumps(state_data)
    )
    
    state_service.redis.get.return_value = stored_state.model_dump_json()
    
    # Execute
    result = await state_service.get_state(
        state_type=state_type,
        state_id=state_id
    )
    
    # Assert
    assert result == state_data


@pytest.mark.asyncio
async def test_delete_state(state_service):
    """Test deleting state"""
    # Setup
    state_id = str(uuid.uuid4())
    state_type = StateType.GENERAL
    
    state_service.redis.delete.return_value = 1
    
    # Execute
    result = await state_service.delete_state(
        state_type=state_type,
        state_id=state_id
    )
    
    # Assert
    assert result is True
    state_service.redis.delete.assert_called_once_with(
        f"state:{state_type}:{state_id}"
    )


@pytest.mark.asyncio
async def test_delete_state_not_found(state_service):
    """Test deleting non-existent state"""
    # Setup
    state_service.redis.delete.return_value = 0
    
    # Execute
    result = await state_service.delete_state(
        state_type=StateType.GENERAL,
        state_id="non-existent"
    )
    
    # Assert
    assert result is False


@pytest.mark.asyncio
async def test_exists(state_service):
    """Test checking if state exists"""
    # Setup
    state_id = str(uuid.uuid4())
    state_type = StateType.GENERAL
    
    state_service.redis.exists.return_value = 1
    
    # Execute
    result = await state_service.exists(
        state_type=state_type,
        state_id=state_id
    )
    
    # Assert
    assert result is True
    state_service.redis.exists.assert_called_once_with(
        f"state:{state_type}:{state_id}"
    )


@pytest.mark.asyncio
async def test_extend_ttl(state_service):
    """Test extending TTL of existing state"""
    # Setup
    state_id = str(uuid.uuid4())
    state_type = StateType.GENERAL
    additional_time = timedelta(minutes=30)
    
    state_service.redis.expire.return_value = True
    
    # Execute
    result = await state_service.extend_ttl(
        state_type=state_type,
        state_id=state_id,
        additional_time=additional_time
    )
    
    # Assert
    assert result is True
    state_service.redis.expire.assert_called_once_with(
        f"state:{state_type}:{state_id}",
        additional_time.total_seconds()
    )


@pytest.mark.asyncio
async def test_update_state(state_service, test_state_data):
    """Test updating existing state"""
    # Setup
    state_id = test_state_data.id
    state_type = StateType.GENERAL
    
    # Mock existing state
    existing_state = State(
        type=state_type,
        data=test_state_data.model_dump_json()
    )
    state_service.redis.get.return_value = existing_state.model_dump_json()
    
    # Update data
    test_state_data.value = 100
    test_state_data.metadata = {"updated": True}
    
    # Execute
    result = await state_service.update_state(
        state_type=state_type,
        state_id=state_id,
        data=test_state_data
    )
    
    # Assert
    assert result is True
    
    # Verify get was called
    state_service.redis.get.assert_called_once()
    
    # Verify set was called with updated data
    state_service.redis.set.assert_called_once()
    call_args = state_service.redis.set.call_args
    stored_data = json.loads(call_args[0][1])
    assert json.loads(stored_data["data"])["value"] == 100


@pytest.mark.asyncio
async def test_bulk_set(state_service):
    """Test setting multiple states at once"""
    # Setup
    states = [
        (StateType.GENERAL, f"id_{i}", {"value": i})
        for i in range(3)
    ]
    
    pipeline = AsyncMock()
    state_service.redis.pipeline.return_value = pipeline
    
    # Execute
    await state_service.bulk_set(states)
    
    # Assert
    assert pipeline.set.call_count == 3
    pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_bulk_get(state_service):
    """Test getting multiple states at once"""
    # Setup
    state_ids = [f"id_{i}" for i in range(3)]
    state_type = StateType.GENERAL
    
    states = []
    for i, state_id in enumerate(state_ids):
        state = State(
            type=state_type,
            data=json.dumps({"id": state_id, "value": i})
        )
        states.append(state.model_dump_json())
    
    pipeline = AsyncMock()
    pipeline.execute.return_value = states
    state_service.redis.pipeline.return_value = pipeline
    
    # Execute
    results = await state_service.bulk_get(
        state_type=state_type,
        state_ids=state_ids
    )
    
    # Assert
    assert len(results) == 3
    assert pipeline.get.call_count == 3
    pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_scan_keys(state_service):
    """Test scanning for keys by pattern"""
    # Setup
    state_type = StateType.GENERAL
    pattern = "*test*"
    
    # Mock scan response
    state_service.redis.scan.return_value = (0, [
        f"state:{state_type}:test_1",
        f"state:{state_type}:test_2"
    ])
    
    # Execute
    keys = await state_service.scan_keys(
        state_type=state_type,
        pattern=pattern
    )
    
    # Assert
    assert len(keys) == 2
    state_service.redis.scan.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_expired(state_service):
    """Test cleaning up expired states"""
    # Setup
    state_type = StateType.GENERAL
    
    # Mock scan to return some keys
    state_service.redis.scan.return_value = (0, [
        f"state:{state_type}:expired_1",
        f"state:{state_type}:expired_2",
        f"state:{state_type}:valid"
    ])
    
    # Mock TTL checks (negative means expired)
    state_service.redis.ttl = AsyncMock(side_effect=[-1, -1, 3600])
    
    # Execute
    deleted_count = await state_service.cleanup_expired(state_type)
    
    # Assert
    assert deleted_count == 2
    assert state_service.redis.delete.call_count == 2


@pytest.mark.asyncio
async def test_get_with_metadata(state_service, test_state_data):
    """Test getting state with metadata"""
    # Setup
    state_id = str(uuid.uuid4())
    state_type = StateType.GENERAL
    
    metadata = {
        "created_at": datetime.now().isoformat(),
        "created_by": "test_user"
    }
    
    stored_state = State(
        type=state_type,
        data=test_state_data.model_dump_json(),
        metadata=metadata
    )
    
    state_service.redis.get.return_value = stored_state.model_dump_json()
    
    # Execute
    result, result_metadata = await state_service.get_with_metadata(
        state_type=state_type,
        state_id=state_id,
        model_class=TestModel
    )
    
    # Assert
    assert isinstance(result, TestModel)
    assert result_metadata == metadata


@pytest.mark.asyncio
async def test_atomic_update(state_service, test_state_data):
    """Test atomic update with optimistic locking"""
    # Setup
    state_id = test_state_data.id
    state_type = StateType.GENERAL
    
    # Mock watch and transaction
    state_service.redis.watch = AsyncMock()
    state_service.redis.multi = AsyncMock()
    
    # Execute update function
    async def update_func(data: TestModel) -> TestModel:
        data.value += 1
        return data
    
    result = await state_service.atomic_update(
        state_type=state_type,
        state_id=state_id,
        update_func=update_func,
        model_class=TestModel
    )
    
    # Assert
    state_service.redis.watch.assert_called_once()


@pytest.mark.asyncio
async def test_create_ephemeral_token(state_service):
    """Test creating ephemeral authentication token"""
    # Setup
    user_id = str(uuid.uuid4())
    
    # Execute
    token = await state_service.create_ephemeral_token(
        user_id=user_id,
        ttl=timedelta(minutes=5)
    )
    
    # Assert
    assert token is not None
    assert len(token) == 36  # UUID format
    
    # Verify token was stored
    state_service.redis.set.assert_called_once()
    call_args = state_service.redis.set.call_args
    assert "auth" in call_args[0][0]
    assert call_args[1]["ex"] == 300  # 5 minutes