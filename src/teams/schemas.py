from pydantic import BaseModel, UUID4, ConfigDict, Field, computed_field, model_validator, root_validator, validator
from typing import List, Optional
from datetime import datetime
from .models import Team, Roster, TeamCaptain
from auth.schemas import PlayerPublic



# Request Schemas
class TeamCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    logo: Optional[str] = None

class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    logo_token_id: str

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
    season_id: UUID4
    model_config = ConfigDict(from_attributes=True)

class TeamCaptainInfo(BaseModel):
    id: UUID4
    player: PlayerPublic
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

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
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TeamDetailed(TeamBase):
    rosters: List[RosterMember]
    captains: List[TeamCaptainInfo]
    max_roster_size: int = Field(default=99) 
    #current_elo_history: Optional[TeamELOHistory]
    @computed_field
    @property
    def active_roster_count(self) ->int:
        return len([x for x in self.rosters if not x.pending])
    
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

class PlayerRosterHistory(BaseModel):
    current: Optional[TeamHistory]
    previous: Optional[List[TeamHistory]]
