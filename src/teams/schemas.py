from pydantic import BaseModel, UUID4, Field
from typing import List, Optional
from datetime import datetime
from .models import Team, Roster, TeamCaptain
from auth.schemas import PlayerPublic

# Request Schemas
class TeamCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    logo: Optional[str] = None

class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    logo: Optional[str] = None

class RosterAddPlayer(BaseModel):
    player_id: UUID4
    season_id: UUID4

class RosterRemovePlayer(BaseModel):
    player_id: UUID4

class TeamCaptainAdd(BaseModel):
    player_id: UUID4

# Response Schemas
class RosterMember(BaseModel):
    player: PlayerPublic
    pending: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TeamCaptainInfo(BaseModel):
    id: UUID4
    player: PlayerPublic
    created_at: datetime

    class Config:
        from_attributes = True

class TeamELOHistory(BaseModel):
    id: UUID4
    elo_rating: int
    player_composition: List[UUID4]
    created_at: datetime
    fixture_id: UUID4

    class Config:
        from_attributes = True

class TeamBase(BaseModel):
    id: UUID4
    name: str
    logo: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TeamDetailed(TeamBase):
    roster: List[RosterMember]
    captains: List[TeamCaptainInfo]
    current_elo_history: Optional[TeamELOHistory]

class TeamBasic(TeamBase):
    active_roster_count: int
    captain_count: int

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

    class Config:
        from_attributes = True

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
