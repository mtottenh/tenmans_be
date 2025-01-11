from pydantic import BaseModel, UUID4, Field, validator
from typing import List, Optional, Dict
from datetime import datetime
from enum import StrEnum

class SeasonState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class TournamentType(StrEnum):
    REGULAR = "regular"
    KNOCKOUT = "knockout"
    PUG = "pug"

class TournamentState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

# Request Schemas
class SeasonCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    start_date: datetime
    end_date: datetime

class TournamentCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    type: TournamentType
    season_id: UUID4
    max_team_size: int = Field(..., ge=5, le=10)
    map_pool: List[UUID4]
    format: Dict[str, any]  # Flexible format configuration

    @validator('format')
    def validate_format(cls, v, values):
        if values['type'] == TournamentType.REGULAR:
            required_keys = {'group_size', 'teams_per_group', 'teams_advancing'}
            if not all(key in v for key in required_keys):
                raise ValueError(f'Format must include {required_keys}')
        return v

class RoundCreate(BaseModel):
    tournament_id: UUID4
    round_number: int
    type: str
    best_of: int
    start_date: datetime
    end_date: datetime

class FixtureCreate(BaseModel):
    tournament_id: UUID4
    round_id: UUID4
    team_1_id: UUID4
    team_2_id: UUID4
    scheduled_at: datetime
    match_format: str = Field(..., pattern="^(bo1|bo3|bo5)$")

class FixtureReschedule(BaseModel):
    new_scheduled_at: datetime
    reason: str

class FixtureForfeit(BaseModel):
    winner_id: UUID4
    reason: str

# Response Schemas
class SeasonBase(BaseModel):
    id: UUID4
    name: str
    state: SeasonState
    created_at: datetime

    class Config:
        from_attributes = True

class TournamentBase(BaseModel):
    id: UUID4
    name: str
    type: TournamentType
    state: TournamentState
    max_team_size: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RoundBase(BaseModel):
    id: UUID4
    round_number: int
    type: str
    best_of: int
    start_date: datetime
    end_date: datetime
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class FixtureBase(BaseModel):
    id: UUID4
    tournament_id: UUID4
    round_id: UUID4
    team_1_id: UUID4
    team_2_id: UUID4
    match_format: str
    scheduled_at: datetime
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Detailed Response Schemas
class SeasonDetailed(SeasonBase):
    tournaments: List[TournamentBase]
    total_teams: int
    total_matches: int

class TournamentDetailed(TournamentBase):
    season: SeasonBase
    rounds: List[RoundBase]
    participating_teams: int
    matches_completed: int
    matches_remaining: int

class RoundDetailed(RoundBase):
    tournament: TournamentBase
    fixtures: List[FixtureBase]

class FixtureDetailed(FixtureBase):
    round: RoundBase
    team_1: "TeamBasic"  # from team schemas
    team_2: "TeamBasic"
    rescheduled_from: Optional[datetime]
    rescheduled_by: Optional["PlayerPublic"]  # from auth schemas
    reschedule_reason: Optional[str]
    forfeit_winner: Optional[UUID4]
    forfeit_reason: Optional[str]
    admin_notes: Optional[str]⎋
