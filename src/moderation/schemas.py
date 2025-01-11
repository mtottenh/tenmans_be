from pydantic import BaseModel, UUID4, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import StrEnum

class BanScope(StrEnum):
    MATCH = "match"
    TOURNAMENT = "tournament"
    SEASON = "season"
    PERMANENT = "permanent"

class BanStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    APPEALED = "appealed"
    REVOKED = "revoked"

# Request Schemas
class BanCreate(BaseModel):
    player_uid: Optional[UUID4] = None
    team_id: Optional[UUID4] = None
    scope: BanScope
    scope_id: Optional[UUID4] = None
    reason: str
    evidence: Optional[str]
    end_date: Optional[datetime]

    @validator('scope_id')
    def validate_scope_id(cls, v, values):
        if values['scope'] != BanScope.PERMANENT and v is None:
            raise ValueError('scope_id required for non-permanent bans')
        return v

    @validator('player_uid', 'team_id')
    def validate_target(cls, v, values):
        if 'player_uid' in values and 'team_id' in values:
            if (values['player_uid'] is None and values['team_id'] is None) or \
               (values['player_uid'] is not None and values['team_id'] is not None):
                raise ValueError('Exactly one of player_uid or team_id must be provided')
        return v

class BanUpdate(BaseModel):
    status: BanStatus
    revoke_reason: Optional[str]

# Response Schemas
class BanBase(BaseModel):
    id: UUID4
    scope: BanScope
    scope_id: Optional[UUID4]
    reason: str
    evidence: Optional[str]
    status: BanStatus
    start_date: datetime
    end_date: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class BanDetailed(BanBase):
    player: Optional["PlayerPublic"]
    team: Optional["TeamBasic"]
    issued_by: "PlayerPublic"
    revoked_by: Optional["PlayerPublic"]
    revoke_reason: Optional[str]
