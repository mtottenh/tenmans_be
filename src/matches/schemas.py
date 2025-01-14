from pydantic import BaseModel, UUID4, ConfigDict, Field, HttpUrl, model_validator
from typing import List, Optional, Self
from datetime import datetime
from enum import StrEnum

class ConfirmationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"

# Request Schemas
class ResultCreate(BaseModel):
    fixture_id: UUID4
    map_id: UUID4
    map_number: int = Field(1, ge=1)
    team_1_score: int = Field(..., ge=0)
    team_2_score: int = Field(..., ge=0)
    team_1_side_first: str = Field(..., pattern="^(CT|T)$")
    demo_url: Optional[HttpUrl]
    screenshot_urls: Optional[List[HttpUrl]]

    @model_validator(mode='after')
    def validate_scores(self) -> Self:
        if self.team_1_score > 100 or self.team_2_score > 100:  # TODO: Max rounds in regulation - set to 100 for now as we haven't got OT sorted
            raise ValueError('Score exceeds maximum possible rounds')
        return self

class ResultConfirm(BaseModel):
    result_id: UUID4
    confirming_captain_id: UUID4

class ResultDispute(BaseModel):
    result_id: UUID4
    reason: str
    evidence_urls: Optional[List[HttpUrl]]

class AdminResultOverride(BaseModel):
    result_id: UUID4
    team_1_score: int
    team_2_score: int
    reason: str

class MatchPlayerAdd(BaseModel):
    fixture_id: UUID4
    player_id: UUID4
    team_id: UUID4
    is_substitute: bool = False

# Response Schemas
class ResultBase(BaseModel):
    id: UUID4
    fixture_id: UUID4
    map_id: UUID4
    map_number: int
    team_1_score: int
    team_2_score: int
    team_1_side_first: str
    confirmation_status: ConfirmationStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ResultDetailed(ResultBase):
    submitted_by: UUID4
    confirmed_by: Optional[UUID4]
    admin_override: bool
    admin_override_by: Optional[UUID4]
    admin_override_reason: Optional[str]
    demo_url: Optional[HttpUrl]
    screenshot_urls: List[HttpUrl]

class MatchPlayerDetail(BaseModel):
    fixture_id: UUID4
    player_id: UUID4
    team_id: UUID4
    is_substitute: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MatchStatsBase(BaseModel):
    kills: int
    deaths: int
    assists: int
    adr: float  # Average Damage per Round
    kast_percentage: float  # Kill/Assist/Survive/Trade Percentage
    hltv_rating: float
    headshot_percentage: float
    first_kills: int
    clutches_won: int

    model_config = ConfigDict(from_attributes=True)

class MatchPlayerStats(MatchStatsBase):
    player_id: UUID4
    match_id: UUID4
    team_id: UUID4
    map_id: UUID4
    created_at: datetime

class MatchSummary(BaseModel):
    fixture_id: UUID4
    maps_played: int
    team_1_maps_won: int
    team_2_maps_won: int
    team_1_total_rounds: int
    team_2_total_rounds: int
    completed_at: datetime
    duration_minutes: int
    has_demos: bool
    has_all_stats: bool

    model_config = ConfigDict(from_attributes=True)
