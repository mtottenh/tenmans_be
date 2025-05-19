from datetime import datetime
from typing import Any, Optional, Self

from pydantic import UUID4, BaseModel, ConfigDict, Field, model_validator

from auth.schemas import PlayerPublic
from competitions.map_pool.schemas import MapPoolResponse
from teams.base_schemas import TeamBasic

from ..base_schemas import (
    GameMode,
    LeagueFormat,
    MapSelectionMethod,
    RegistrationStatus,
    TournamentBase,
    TournamentRegistrationBase,
    TournamentType,
)


class TournamentBasicUpdate(BaseModel):
    """Basic tournament properties that can be updated"""

    name: Optional[str] = Field(None, min_length=3, max_length=50)
    max_team_size: Optional[int] = Field(None, ge=5, le=10)
    min_team_size: Optional[int] = Field(None, ge=5, le=10)


class SwissConfig(BaseModel):
    """Configuration specific to Swiss system tournaments"""

    num_rounds: int = Field(..., gt=0)
    points_for_win: int = Field(default=3)
    points_for_draw: int = Field(default=1)
    tiebreaker_priority: list[str] = Field(
        default=["buchholz", "head_to_head", "rounds_won"]
    )


class KnockoutConfig(BaseModel):
    """Configuration specific to knockout tournaments"""

    third_place_match: bool = False
    consolation_bracket: bool = False
    double_elimination: bool = False


class TournamentCreate(BaseModel):
    """Schema for tournament creation requests"""

    name: str = Field(..., min_length=3, max_length=50)
    season_id: UUID4
    type: TournamentType
    game_mode: GameMode = GameMode.COMPETITIVE_5V5
    league_format: LeagueFormat = LeagueFormat.SINGLE_ROUND_ROBIN
    map_selection_method: MapSelectionMethod = MapSelectionMethod.MAP_VETO

    # Team configuration
    min_teams: int = Field(default=2, ge=2)
    max_teams: int = Field(default=16, ge=2)
    min_team_size: int = Field(default=5, ge=5, le=10)
    max_team_size: int = Field(default=10, ge=5, le=10)

    # Scheduling
    registration_start: datetime
    registration_end: datetime
    scheduled_start_date: datetime
    scheduled_end_date: datetime
    late_registration_end: Optional[datetime] = None
    allow_late_registration: bool = False

    # Configuration
    format_config: dict[str, Any]
    seeding_config: dict[str, Any] = Field(default_factory=dict)
    scheduling_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.registration_end >= self.scheduled_start_date:
            raise ValueError("Registration must end before tournament starts")

        if self.scheduled_end_date <= self.scheduled_start_date:
            raise ValueError("End date must be after start date")

        if (self.allow_late_registration and self.late_registration_end and
            self.late_registration_end >= self.scheduled_start_date):
                raise ValueError("Late registration must end before tournament starts")

        return self


class SeedingPreview(BaseModel):
    """Preview of tournament seeding"""

    seeding_type: str
    seeded_teams: list[TeamBasic]
    seed_details: dict[str, Any]


class TournamentConfigUpdate(BaseModel):
    """Schema for updating tournament configuration"""

    game_mode: Optional[GameMode] = None
    league_format: Optional[LeagueFormat] = None
    map_selection_method: Optional[MapSelectionMethod] = None
    format_config: Optional[dict[str, Any]] = None
    seeding_config: Optional[dict[str, Any]] = None
    scheduling_config: Optional[dict[str, Any]] = None

    # Team limits
    min_teams: Optional[int] = Field(None, ge=2)
    max_teams: Optional[int] = Field(None, ge=2)
    min_team_size: Optional[int] = Field(None, ge=5, le=10)
    max_team_size: Optional[int] = Field(None, ge=5, le=10)

    @model_validator(mode="after")
    def validate_team_sizes(self) -> Self:
        if self.min_team_size and self.max_team_size and self.min_team_size > self.max_team_size:
                raise ValueError("Min team size cannot be greater than max team size")
        if self.min_teams and self.max_teams and self.min_teams > self.max_teams:
                raise ValueError("Min teams cannot be greater than max teams")
        return self


class TournamentConfigResponse(BaseModel):
    """Response schema for tournament configuration"""

    id: UUID4
    name: str
    type: TournamentType
    game_mode: GameMode
    league_format: LeagueFormat
    map_selection_method: MapSelectionMethod
    format_config: dict[str, Any]
    seeding_config: dict[str, Any]
    scheduling_config: dict[str, Any]

    # Team limits
    min_teams: int
    max_teams: int
    min_team_size: int
    max_team_size: int

    # Map pool info if exists
    map_pool: Optional[MapPoolResponse]

    model_config = ConfigDict(from_attributes=True)


class LinkedTournamentRequest(BaseModel):
    """Request schema for linking tournaments"""

    target_tournament_id: UUID4
    qualification_rules: dict[str, Any] = Field(
        default_factory=lambda: {
            "qualify_top": 8,
            "tiebreaker_rules": [
                "head_to_head",
                "round_difference",
                "total_rounds_won",
            ],
        }
    )


class LinkedTournamentResponse(BaseModel):
    """Response schema for linked tournaments"""

    id: UUID4
    source_tournament_id: UUID4
    target_tournament_id: UUID4
    qualification_rules: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
class TournamentRegistrationResponse(BaseModel):
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
    registrations: list[TournamentRegistrationBase]


# Response Schemas
class TournamentWithStats(TournamentBase):
    """Tournament response with additional statistics"""

    total_teams: int
    total_matches: int
    matches_completed: int
    matches_remaining: int
    current_round: Optional[int]
    map_pool: list[UUID4]
    format_config: dict[str, Any]


class TournamentTeam(BaseModel):
    """Schema for teams in a tournament"""

    team_id: UUID4
    matches_played: int
    matches_won: int
    matches_lost: int
    points: int
    status: str  # "active", "eliminated", "qualified", etc.
    final_position: Optional[int] = (
        None  # Final position in the tournament (if completed)
    )

    model_config = ConfigDict(from_attributes=True)


class TournamentStandings(BaseModel):
    """Schema for tournament standings"""

    tournament_id: UUID4
    round: Optional[int]
    teams: list[TournamentTeam]
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


class TournamentRegistrationSummary(BaseModel):
    """List of tournament registrations with summary stats"""

    total_registered: int
    total_pending: int
    registrations: list[TournamentRegistrationBase]

    model_config = ConfigDict(from_attributes=True)


class TournamentPageStats(BaseModel):
    active_tournaments: int
    enrolled_teams: int


class TournamentPage(BaseModel):
    """Paginated tournament response"""

    items: list[TournamentBase]
    total: int
    page: int
    size: int
    stats: TournamentPageStats
    total_pages: int
    has_next: bool
    has_previous: bool
