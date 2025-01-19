from datetime import datetime
from enum import StrEnum
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
import uuid

from auth.schemas import PlayerPublic
from teams.base_schemas import TeamBasic

class JoinRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"  # If player cancels their request
    EXPIRED = "expired"      # If request times out

# Request Schemas
class JoinRequestCreate(BaseModel):
    """Schema for creating a join request"""
    message: Optional[str] = None

class JoinRequestResponse(BaseModel):
    """Schema for responding to a join request"""
    response_message: Optional[str] = None

class JoinRequestBase(BaseModel):
    """Base schema for join requests"""
    id: uuid.UUID
    status: JoinRequestStatus
    message: Optional[str]
    created_at: datetime
    updated_at: datetime
    responded_at: Optional[datetime]
    response_message: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class JoinRequestDetailed(JoinRequestBase):
    """Detailed join request information"""
    player_id: uuid.UUID
    team_id: uuid.UUID
    season_id: uuid.UUID
    responded_by: Optional[uuid.UUID]
    
    # Include nested objects
    player: PlayerPublic  # From your auth schemas
    team: TeamBasic      # From your team schemas
    responder: Optional[PlayerPublic]

    model_config = ConfigDict(from_attributes=True)

class JoinRequestList(BaseModel):
    """List of join requests with summary stats"""
    total: int
    pending_count: int
    requests: List[JoinRequestDetailed]

    model_config = ConfigDict(from_attributes=True)

# Update schemas
class JoinRequestUpdate(BaseModel):
    """Schema for updating a join request status"""
    status: JoinRequestStatus
    response_message: Optional[str] = None

class JoinRequestStats(BaseModel):
    """Statistics for join requests"""
    total_requests: int
    pending_requests: int
    approved_requests: int
    rejected_requests: int
    cancelled_requests: int
    expired_requests: int
    average_response_time: Optional[float] = None  # in hours
    
    model_config = ConfigDict(from_attributes=True)