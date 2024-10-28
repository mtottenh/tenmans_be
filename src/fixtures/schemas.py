from pydantic import BaseModel
import uuid
from datetime import datetime
from .models import ResultEnum

class FixtureCreateModel(BaseModel):
    season: str
    team_1: str
    team_2: str
    scheduled_at: str

class ResultCreateModel(BaseModel):
    fixture_id: str
    result: ResultEnum
    winning_team: str | None
