from pydantic import BaseModel, UUID4, ConfigDict, Field, model_validator
from typing import List, Optional, Self
from datetime import datetime
from enum import StrEnum
from auth.schemas import PlayerPublic
from teams.schemas import TeamBasic
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


    @model_validator(mode='after')
    def validate_scope_id(self) -> Self:
        if self.scope != BanScope.PERMANENT and self.scope_id is None:
            raise ValueError('scope_id required for non-permanent bans')
        return self

    @model_validator(mode='after')
    def validate_target(self) -> Self:
        if self.player_uid is not None and self.team_id is not None:
            raise ValueError('Exactly one of player_uid or team_id must be provided')
        return self

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

    model_config = ConfigDict(from_attributes=True)

class BanDetailed(BanBase):
    player: Optional[PlayerPublic]
    team: Optional[TeamBasic]
    issued_by: PlayerPublic
    revoked_by: Optional[PlayerPublic]
    revoke_reason: Optional[str]
