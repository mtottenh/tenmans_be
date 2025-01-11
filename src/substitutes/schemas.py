from pydantic import BaseModel, UUID4, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import StrEnum

class SubstituteAvailabilityCreate(BaseModel):
    tournament_id: Optional[UUID4]
    season_id: Optional[UUID4]
    is_available: bool = True
    availability_notes: Optional[str]

    @validator('tournament_id', 'season_id')
    def validate_scope(cls, v, values):
        if 'tournament_id' in values and 'season_id' in values:
            if (values['tournament_id'] is not None and values['season_id'] is not None):
                raise ValueError('Cannot be available for both tournament and season')
        return v

class SubstituteAvailabilityUpdate(BaseModel):
    is_available: bool
    availability_notes: Optional[str]

class SubstituteBase(BaseModel):
    id: UUID4
    player_uid: UUID4
    tournament_id: Optional[UUID4]
    season_id: Optional[UUID4]
    is_available: bool
    availability_notes: Optional[str]
    last_substitute_date: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class SubstituteDetailed(SubstituteBase):
    player: "PlayerPublic"
    tournament: Optional["TournamentBase"]
    season: Optional["SeasonBase"]
