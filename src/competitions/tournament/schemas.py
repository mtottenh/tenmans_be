from pydantic import BaseModel, ConfigDict, Field, UUID4
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..base_schemas import TournamentType, RegistrationStatus, TournamentBase, TournamentRegistrationBase


# Request Schemas
class TournamentCreate(BaseModel):
    """Schema for tournament creation requests"""
    name: str = Field(..., min_length=3, max_length=50)
    season_id: UUID4
    type: TournamentType
    max_team_size: int = Field(..., ge=5, le=10)
    map_pool: List[UUID4]
    format_config: Dict[str, Any]  # Flexible tournament format configuration

class TournamentUpdate(BaseModel):
    """Schema for tournament update requests"""
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    max_team_size: Optional[int] = Field(None, ge=5, le=10)
    map_pool: Optional[List[UUID4]]
    format_config: Optional[Dict[str, Any]]


class TournamentRegistrationRequest(BaseModel):
    """Schema for tournament registration requests"""
    team_id: UUID4
    notes: Optional[str] = None

class RegistrationReviewRequest(BaseModel):
    """Schema for reviewing registration requests"""
    status: RegistrationStatus
    notes: Optional[str] = None

class RegistrationWithdrawRequest(BaseModel):
    """Schema for withdrawing from a tournament"""
    reason: str

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
    team_name: str
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



class TournamentRegistrationDetail(TournamentRegistrationBase):
    """Detailed tournament registration response"""
    requested_by: UUID4
    reviewed_by: Optional[UUID4]
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    withdrawn_by: Optional[UUID4]
    withdrawn_at: Optional[datetime]
    withdrawal_reason: Optional[str]

class TournamentRegistrationList(BaseModel):
    """List of tournament registrations with summary stats"""
    total_registered: int
    total_pending: int
    registrations: List[TournamentRegistrationBase]

    model_config = ConfigDict(from_attributes=True)