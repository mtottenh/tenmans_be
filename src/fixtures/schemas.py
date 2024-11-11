
from pydantic import BaseModel
from datetime import datetime

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
