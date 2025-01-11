from redis import asyncio as aioredis
from typing import Optional, TypeVar, Generic, Any
from pydantic import BaseModel
from enum import StrEnum
import json
import uuid
from datetime import timedelta
from fastapi import Depends
from src.config import Config

T = TypeVar('T', bound=BaseModel)

class StateType(StrEnum):
    AUTH = "auth"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"
    FILE_UPLOAD = "file_upload"
    GENERAL = "general"

class State(BaseModel):
    """Base model for state data"""
    type: StateType
    data: dict[str, Any]
    metadata: Optional[dict[str, Any]] = None

class StateService:
    """Service for managing temporary state data"""
    
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)
        self.expiry_times = {
            StateType.AUTH: timedelta(minutes=5),
            StateType.PASSWORD_RESET: timedelta(hours=24),
            StateType.EMAIL_VERIFICATION: timedelta(hours=48),
            StateType.FILE_UPLOAD: timedelta(minutes=30),
            StateType.GENERAL: timedelta(minutes=15),
        }
    
    def _get_key(self, state_type: StateType, state_id: str) -> str:
        """Generate Redis key for state"""
        return f"state:{state_type}:{state_id}"
    
    async def store_state(
        self,
        state_type: StateType,
        data: BaseModel,
        metadata: Optional[dict] = None,
        custom_expiry: Optional[timedelta] = None
    ) -> str:
        """Store state data and return state ID"""
        state_id = str(uuid.uuid4())
        key = self._get_key(state_type, state_id)
        
        state = State(
            type=state_type,
            data=data.model_dump(),
            metadata=metadata
        )
        
        expiry = custom_expiry or self.expiry_times[state_type]
        
        await self.redis.setex(
            key,
            expiry,
            json.dumps(state.model_dump())
        )
        
        return state_id
    
    async def retrieve_state(
        self,
        state_type: StateType,
        state_id: str,
        model_class: type[T],
        delete: bool = True
    ) -> Optional[tuple[T, Optional[dict]]]:
        """
        Retrieve state data and optionally delete it
        Returns tuple of (data, metadata) if found, None if not found
        """
        key = self._get_key(state_type, state_id)
        data = await self.redis.get(key)
        
        if not data:
            return None
            
        if delete:
            await self.redis.delete(key)
            
        state = State.model_validate(json.loads(data))
        return model_class.model_validate(state.data), state.metadata
    
    async def extend_expiry(
        self,
        state_type: StateType,
        state_id: str,
        extension: timedelta
    ) -> bool:
        """Extend expiry time of state"""
        key = self._get_key(state_type, state_id)
        return await self.redis.expire(key, extension)
    
    async def delete_state(self, state_type: StateType, state_id: str) -> bool:
        """Delete state data"""
        key = self._get_key(state_type, state_id)
        deleted = await self.redis.delete(key)
        return deleted > 0

# FastAPI dependency
async def get_state_service():
    """Dependency to get StateService instance"""
    return StateService(Config.REDIS_URL)
