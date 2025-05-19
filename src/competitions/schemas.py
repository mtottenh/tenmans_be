from datetime import datetime

from pydantic import UUID4, BaseModel, Field

from .base_schemas import FixtureBase, RoundBase, SeasonBase, TournamentBase


# Request Schemas
class SeasonCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    # start_date: datetime
    # end_date: datetime


class RoundCreate(BaseModel):
    tournament_id: UUID4
    round_number: int
    type: str
    best_of: int
    start_date: datetime
    end_date: datetime


# Detailed Response Schemas
class SeasonDetailed(SeasonBase):
    tournaments: list[TournamentBase]
    total_teams: int
    total_matches: int


class RoundDetailed(RoundBase):
    tournament: TournamentBase
    fixtures: list[FixtureBase]
