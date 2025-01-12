from pydantic import BaseModel, UUID4, Field
from typing import List
from datetime import datetime
from .base_schemas import TournamentBase, RoundBase, SeasonBase, FixtureBase


# Request Schemas
class SeasonCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    start_date: datetime
    end_date: datetime

class RoundCreate(BaseModel):
    tournament_id: UUID4
    round_number: int
    type: str
    best_of: int
    start_date: datetime
    end_date: datetime


# Detailed Response Schemas
class SeasonDetailed(SeasonBase):
    tournaments: List[TournamentBase]
    total_teams: int
    total_matches: int


class RoundDetailed(RoundBase):
    tournament: TournamentBase
    fixtures: List[FixtureBase]

