from pydantic import BaseModel, UUID4, ConfigDict, Field, model_validator, validator
from typing import List, Optional, Self
from datetime import datetime
from auth.schemas import PlayerPublic
from competitions.schemas import RoundBase
from matches.schemas import ResultBase
from teams.base_schemas import TeamBasic
from ..base_schemas import FixtureBase, MatchPlayerBase, FixtureStatus

# Match Player Schemas
class MatchPlayerCreate(BaseModel):
    """Schema for adding a player to a match"""
    fixture_id: UUID4
    player_id: UUID4
    team_id: UUID4
    is_substitute: bool = False

# Request Schemas
class FixtureCreate(BaseModel):
    """Schema for creating a new fixture"""
    tournament_id: UUID4
    round_id: UUID4
    team_1: UUID4
    team_2: UUID4
    match_format: str = Field(..., pattern="^(bo1|bo3|bo5)$")
    scheduled_at: datetime

    @model_validator(mode='after')
    def teams_must_be_different(self) -> Self:
        if self.team_1 == self.team_2:
            raise ValueError('team_1 and team_2 cannot be the same')
        return self

class FixtureUpdate(BaseModel):
    """Schema for updating a fixture"""
    scheduled_at: Optional[datetime] = None
    status: Optional[FixtureStatus] = None
    admin_notes: Optional[str] = None

class FixtureReschedule(BaseModel):
    """Schema for rescheduling a fixture"""
    scheduled_at: datetime
    rescheduled_by: UUID4
    reschedule_reason: str

class FixtureForfeit(BaseModel):
    """Schema for marking a fixture as forfeited"""
    forfeit_winner: UUID4
    forfeit_reason: str


# Response Schemas

class MatchPlayerDetailed(MatchPlayerBase):
    """Detailed match player response with relationships"""
    player: PlayerPublic
    team: TeamBasic
    fixture: FixtureBase

    model_config = ConfigDict(from_attributes=True)

class FixtureDetailed(FixtureBase):
    """Detailed fixture response schema"""
    rescheduled_from: Optional[datetime]
    rescheduled_by: Optional[UUID4]
    reschedule_reason: Optional[str]
    forfeit_winner: Optional[UUID4]
    forfeit_reason: Optional[str]
    admin_notes: Optional[str]

    # Include relationships
    team_1_rel: TeamBasic
    team_2_rel: TeamBasic
    round: RoundBase
    match_players: List[MatchPlayerBase]
    results: List[ResultBase]
    model_config = ConfigDict(from_attributes=True)

class FixtureSummary(BaseModel):
    """Summary of a fixture's status and results"""
    id: UUID4
    tournament_id: UUID4
    round_id: UUID4
    team_1: UUID4
    team_2: UUID4
    status: FixtureStatus
    scheduled_at: datetime
    team_1_score: Optional[int]  # Total maps/games won
    team_2_score: Optional[int]
    completed_at: Optional[datetime]
    is_forfeit: bool
    winner_id: Optional[UUID4]

    model_config = ConfigDict(from_attributes=True)

class UpcomingFixturesResponse(BaseModel):
    """Response model for upcoming fixtures"""
    items: List[FixtureBase]
    total: int
    next_24h: int  # Fixtures in next 24 hours
    next_week: int  # Fixtures in next 7 days

class FixturePage(BaseModel):
    """Paginated fixture response"""
    items: List[FixtureBase]
    total: int
    page: int 
    size: int
    has_next: bool
    has_previous: bool

class FixtureList(BaseModel):
    """List of fixtures with pagination metadata"""
    total: int
    items: List[FixtureBase]
    scheduled_count: int
    completed_count: int
    cancelled_count: int
    forfeited_count: int

    model_config = ConfigDict(from_attributes=True)



# Team ELO History Schemas
class TeamELOHistoryCreate(BaseModel):
    """Schema for creating team ELO history entry"""
    team_id: UUID4
    fixture_id: UUID4
    elo_rating: int
    player_composition: List[UUID4]


# Stats and Analytics Schemas
class FixtureStats(BaseModel):
    """Statistics for a fixture"""
    fixture_id: UUID4
    total_rounds_played: int
    average_round_time: float  # in seconds
    total_timeouts_used: int
    total_pauses: int
    total_technical_issues: int
    match_duration: int  # in minutes
    has_demos: bool
    has_complete_stats: bool

    model_config = ConfigDict(from_attributes=True)

class TeamPerformance(BaseModel):
    """Team performance metrics in a fixture"""
    team_id: UUID4
    rounds_won: int
    rounds_lost: int
    t_rounds_won: int
    ct_rounds_won: int
    timeouts_used: int
    clutches_won: int
    eco_rounds_won: int
    objective_rounds_won: int  # bomb plants/defuses

    model_config = ConfigDict(from_attributes=True)