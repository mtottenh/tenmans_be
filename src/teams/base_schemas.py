# Request Schemas
from datetime import datetime
from enum import StrEnum
from typing import List, Optional
from pydantic import UUID4, BaseModel, ConfigDict, Field

class TeamStatus(StrEnum):
    ACTIVE = "active"
    DISBANDED = "disbanded"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"

class RosterStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"
    REMOVED = "REMOVED"
    PAST = "PAST"
    SUSPENDED = "SUSPENDED"

class TeamCaptainStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"
    REMOVED = "REMOVED"
    TEMPORARY = "TEMPORARY"
    DISBANDED = "DISBANDED"

class RecruitmentStatus(StrEnum):
    ACTIVE = "recruiting"
    CLOSED = "closed"

class TeamCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    logo: Optional[str] = None

class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    logo_token_id: str

class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    logo_token_id: Optional[str] = None
    #max_roster_size: int
    recruitment_status: bool

class RosterAddPlayer(BaseModel):
    player_id: UUID4
    season_id: UUID4

class RosterRemovePlayer(BaseModel):
    player_id: UUID4

class TeamCaptainAdd(BaseModel):
    player_id: UUID4


class TeamELOHistory(BaseModel):
    id: UUID4
    elo_rating: int
    player_composition: List[UUID4]
    created_at: datetime
    fixture_id: UUID4

    model_config = ConfigDict(from_attributes=True)

class TeamBase(BaseModel):
    id: UUID4
    name: str
    logo: Optional[str]
    recruitment_status: RecruitmentStatus
    status: TeamStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TeamBasic(TeamBase):
    pass
    # TODO - 
    # active_roster_count: int
    # captain_count: int

class TeamStats(BaseModel):
    team_id: UUID4
    matches_played: int
    matches_won: int
    matches_lost: int
    rounds_won: int
    rounds_lost: int
    current_win_streak: int
    highest_win_streak: int
    average_team_elo: float

    model_config = ConfigDict(from_attributes=True)


# Special purpose schemas
class TeamInviteResponse(BaseModel):
    team_id: UUID4
    player_id: UUID4
    status: str  # 'accepted', 'rejected', 'pending'
    responded_at: Optional[datetime]

class TeamSeasonStats(TeamStats):
    season_id: UUID4
    season_name: str
    tournament_participations: int


class TeamHistory(BaseModel):
    team_id: UUID4
    name: str
    season_id: UUID4
    since: datetime
    status: TeamStatus
    is_captain: bool

