# availability/schemas.py
from pydantic import BaseModel, UUID4, Field
from typing import List, Optional, Dict
from datetime import datetime
from competitions.models.scheduling import AvailabilityType, AvailabilityStatus

class AvailabilityCreate(BaseModel):
    tournament_id: Optional[UUID4] = None
    start_time: datetime
    end_time: datetime
    availability_type: AvailabilityType
    is_substitute: bool = False
    notes: Optional[str] = None
    recurring: bool = False
    recurring_pattern: Optional[Dict] = None

class AvailabilityResponse(BaseModel):
    id: UUID4
    player_id: UUID4
    tournament_id: Optional[UUID4]
    start_time: datetime
    end_time: datetime
    availability_type: AvailabilityType
    status: AvailabilityStatus
    is_substitute: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TeamAvailabilityResponse(BaseModel):
    id: UUID4
    team_id: UUID4
    tournament_id: UUID4
    date: datetime
    available_players: List[UUID4]
    maybe_players: List[UUID4]
    unavailable_players: List[UUID4]
    available_substitutes: List[UUID4]
    has_minimum_players: bool
    updated_at: datetime

    class Config:
        from_attributes = True

class ScheduleSuggestionResponse(BaseModel):
    suggested_time: datetime
    confidence_score: float
    available_players_team1: int
    available_players_team2: int
    conflicts: List[Dict]

    class Config:
        from_attributes = True