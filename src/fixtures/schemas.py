
from pydantic import BaseModel
from typing import List, Union, Literal


class FixtureDate(BaseModel):
    scheduled_at: str


class FixtureCreateModel(BaseModel):
    season: str
    team_1: str
    team_2: str
    scheduled_at: str


class ResultConfirmModel(BaseModel):
    fixture_id: str

class ResultCreateModel(BaseModel):
    fixture_id: str
    score_team_1: int
    score_team_2: int


class PugCreateModel(BaseModel):
    team_1: str
    team_2: str
    map_pool: List[str]
    match_format: Literal['bo1'] | Literal['bo3']
