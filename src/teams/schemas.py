from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import List

class TeamCreateModel(BaseModel):
    name: str

class TeamUpdateModel(BaseModel):
    name: str

class SeasonCreateModel(BaseModel):
    name: str

class RosterUpdateModel(BaseModel):
    players: List[str]