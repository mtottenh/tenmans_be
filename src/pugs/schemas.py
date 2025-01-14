from pydantic import BaseModel, UUID4, ConfigDict, Field, model_validator
from typing import List, Optional, Self
from datetime import datetime
from enum import StrEnum

class PugStatus(StrEnum):
    CREATING = "creating"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

# Request Schemas
class PugCreate(BaseModel):
    match_format: str = Field(..., pattern="^(bo1|bo3)$")
    max_players_per_team: int = Field(..., ge=1, le=5)
    require_full_teams: bool = True
    map_pool: List[UUID4]

class PugTeamCreate(BaseModel):
    pug_id: UUID4
    team_number: int = Field(..., ge=1, le=2)
    team_name: str
    captain_id: UUID4

    @model_validator(mode='after')
    def validate_team_number(self) -> Self:
        if self.team_number not in [1, 2]:
            raise ValueError('team_number must be 1 or 2')
        return self

class PugPlayerJoin(BaseModel):
    pug_id: UUID4
    team_number: Optional[int] = Field(None, ge=1, le=2)

class PugMapResult(BaseModel):
    pug_id: UUID4
    map_number: int
    map_id: UUID4
    team_1_score: int
    team_2_score: int
    team_1_side_first: str = Field(..., pattern="^(CT|T)$")
    demo_url: Optional[str]

# Response Schemas
class PugBase(BaseModel):
    id: UUID4
    status: PugStatus
    match_format: str
    max_players_per_team: int
    require_full_teams: bool
    created_by: UUID4
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

class PugTeamBase(BaseModel):
    pug_id: UUID4
    team_number: int
    team_name: str
    captain_id: UUID4
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PugPlayerBase(BaseModel):
    pug_id: UUID4
    player_id: UUID4
    team_number: Optional[int]
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PugMapResultBase(BaseModel):
    id: UUID4
    pug_id: UUID4
    map_number: int
    map_id: UUID4
    team_1_score: int
    team_2_score: int
    team_1_side_first: str
    demo_url: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Detailed Response Schemas
class PugTeamDetailed(PugTeamBase):
    players: List[PugPlayerBase]
    total_players: int

class PugDetailed(PugBase):
    teams: List[PugTeamDetailed]
    map_results: List[PugMapResultBase]
    available_maps: List[UUID4]
    player_count: int
    is_ready_to_start: bool

class PugSummary(BaseModel):
    pug_id: UUID4
    status: PugStatus
    team_1_name: str
    team_2_name: str
    maps_played: int
    team_1_maps_won: int
    team_2_maps_won: int
    created_at: datetime
    completed_at: Optional[datetime]
    total_players: int

    model_config = ConfigDict(from_attributes=True)
