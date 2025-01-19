from pydantic import BaseModel, UUID4, ConfigDict
from typing import List, Optional
from datetime import datetime
from enum import StrEnum

class SeasonState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class FixtureStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FORFEITED = "forfeited"


class RegistrationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    DISQUALIFIED = "disqualified"


class TournamentType(StrEnum):
    REGULAR = "regular"
    KNOCKOUT = "knockout"
    PUG = "pug"

class TournamentState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"



# Response Schemas
class SeasonBase(BaseModel):
    id: UUID4
    name: str
    state: SeasonState
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)


class TeamELOHistoryBase(BaseModel):
    """Base schema for team ELO history response"""
    id: UUID4
    team_id: UUID4
    fixture_id: UUID4
    elo_rating: int
    player_composition: List[UUID4]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)



class MatchPlayerBase(BaseModel):
    """Base schema for match player response"""
    fixture_id: UUID4
    player_id: UUID4
    team_id: UUID4
    is_substitute: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FixtureBase(BaseModel):
    """Base fixture response schema"""
    id: UUID4
    tournament_id: UUID4
    round_id: UUID4
    team_1: UUID4
    team_2: UUID4
    match_format: str
    scheduled_at: datetime
    status: FixtureStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TournamentBase(BaseModel):
    """Base tournament response schema"""
    id: UUID4
    name: str
    type: TournamentType
    state: TournamentState
    season_id: UUID4
    max_team_size: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TournamentRegistrationBase(BaseModel):
    """Base schema for tournament registration responses"""
    id: UUID4
    tournament_id: UUID4
    team_id: UUID4
    status: RegistrationStatus
    requested_at: datetime
    seed: Optional[int]
    group: Optional[str]
    final_position: Optional[int]

    model_config = ConfigDict(from_attributes=True)