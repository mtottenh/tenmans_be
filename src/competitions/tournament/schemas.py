from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, UUID4
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..base_schemas import TournamentType, RegistrationStatus, TournamentBase, TournamentRegistrationBase
from teams.base_schemas import TeamBasic
from auth.schemas import PlayerPublic

# Request Schemas
class TournamentCreate(BaseModel):
    """Schema for tournament creation requests"""
    name: str = Field(..., min_length=3, max_length=50)
    season_id: UUID4
    type: TournamentType
    registration_start: datetime
    registration_end: datetime
    scheduled_start: datetime
    scheduled_end: datetime
    max_team_size: int = Field(..., ge=1, le=100)
    map_pool: List[UUID4]
    format_config: Dict[str, Any]  # Flexible tournament format configuration

class TournamentUpdate(BaseModel):
    """Schema for tournament update requests"""
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    max_team_size: Optional[int] = Field(None, ge=5, le=10)
    map_pool: Optional[List[UUID4]]
    format_config: Optional[Dict[str, Any]]


# Request Schemas
class TournamentRegistrationRequest(BaseModel):
    """Schema for requesting tournament registration"""
    team_id: UUID4
    notes: Optional[str] = None
    requested_by: UUID4  
    requested_at: datetime
    tournament_id: UUID4 

class RegistrationReviewRequest(BaseModel):
    """Schema for reviewing a registration request"""
    status: RegistrationStatus
    review_notes: Optional[str] = None
    reviewed_by: UUID4  
    reviewed_at: datetime  

class RegistrationWithdrawRequest(BaseModel):
    """Schema for withdrawing from a tournament"""
    reason: str
    withdrawn_by: UUID4  
    withdrawn_at: datetime 

# Response Schemas
class TournamentRegistrationBase(BaseModel):
    """Base schema for tournament registrations"""
    id: UUID4
    tournament_id: UUID4
    team_id: UUID4 
    status: RegistrationStatus
    
    # Request details
    requested_by: UUID4
    requested_at: datetime
    notes: Optional[str] = None
    
    # Review details
    reviewed_by: Optional[UUID4] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    
    # Withdrawal details
    withdrawn_by: Optional[UUID4] = None
    withdrawn_at: Optional[datetime] = None
    withdrawal_reason: Optional[str] = None
    
    # Tournament specific fields
    seed: Optional[int] = None
    group: Optional[str] = None
    final_position: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class TournamentRegistrationDetail(TournamentRegistrationBase):
    """Detailed registration response including relationships"""
    team: TeamBasic  
    requester: PlayerPublic
    reviewer: Optional[PlayerPublic] = None

class TournamentRegistrationList(BaseModel):
    """List of tournament registrations with summary stats"""
    total: int
    pending_count: int
    registrations: List[TournamentRegistrationBase]

# Response Schemas
class TournamentWithStats(TournamentBase):
    """Tournament response with additional statistics"""
    total_teams: int
    total_matches: int
    matches_completed: int
    matches_remaining: int
    current_round: Optional[int]
    map_pool: List[UUID4]
    format_config: Dict[str, Any]

class TournamentTeam(BaseModel):
    """Schema for teams in a tournament"""
    team_id: UUID4
    matches_played: int
    matches_won: int
    matches_lost: int
    points: int
    status: str  # "active", "eliminated", "qualified", etc.

    model_config = ConfigDict(from_attributes=True)

class TournamentStandings(BaseModel):
    """Schema for tournament standings"""
    tournament_id: UUID4
    round: Optional[int]
    teams: List[TournamentTeam]
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)
# TODO - I don't know if we need this.
# class TournamentDetailed(TournamentBase):
#     season: SeasonBase
#     rounds: List[RoundBase]
#     participating_teams: int
#     matches_completed: int
#     matches_remaining: int


class TournamentRegistrationList(BaseModel):
    """List of tournament registrations with summary stats"""
    total_registered: int
    total_pending: int
    registrations: List[TournamentRegistrationBase]

    model_config = ConfigDict(from_attributes=True)

class TournamentPageStats(BaseModel):
    active_tournaments: int
    enrolled_teams: int

class TournamentPage(BaseModel):
    """Paginated tournament response"""
    items: List[TournamentBase]
    total: int
    page: int
    size: int
    stats: TournamentPageStats
    total_pages: int
    has_next: bool
    has_previous: bool

