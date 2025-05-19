from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional, Self

from pydantic import UUID4, BaseModel, ConfigDict, model_validator


if TYPE_CHECKING:
    from auth.schemas import PlayerPublic
    from competitions.base_schemas import SeasonBase, TournamentBase


class SubstituteAvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    CONDITIONAL = "CONDITIONAL"
    USED = "USED"
    EXCLUDED = "EXCLUDED"


class SubstituteAvailabilityCreate(BaseModel):
    tournament_id: Optional[UUID4]
    season_id: Optional[UUID4]
    is_available: bool = True
    availability_notes: Optional[str]

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.tournament_id is not None and self.season_id is not None:
            raise ValueError("Cannot be available for both tournament and season")
        return self


class SubstituteAvailabilityUpdate(BaseModel):
    is_available: bool
    availability_notes: Optional[str]


class SubstituteBase(BaseModel):
    id: UUID4
    player_id: UUID4
    tournament_id: Optional[UUID4]
    season_id: Optional[UUID4]
    is_available: bool
    availability_notes: Optional[str]
    last_substitute_date: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubstituteDetailed(SubstituteBase):
    player: "PlayerPublic"
    tournament: Optional["TournamentBase"]
    season: Optional["SeasonBase"]
