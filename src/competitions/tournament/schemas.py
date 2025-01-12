from pydantic import BaseModel, Field, UUID4
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import StrEnum

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

# Response Schemas
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

    class Config:
        from_attributes = True

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

    class Config:
        from_attributes = True

class TournamentStandings(BaseModel):
    """Schema for tournament standings"""
    tournament_id: UUID4
    round: Optional[int]
    teams: List[TournamentTeam]
    last_updated: datetime

    class Config:
        from_attributes = True