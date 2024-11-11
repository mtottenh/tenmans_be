from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import List, Union
from src.players.models import Player

class TeamCreateModel(BaseModel):
    name: str

class TeamUpdateModel(BaseModel):
    name: str

class PlayerId(BaseModel):
    id: str

class PlayerName(BaseModel):
    name: str

class RosterUpdateModel(BaseModel):
    players: List[Union[PlayerId,PlayerName]]

class RosterPendingUpdateModel(BaseModel):
    player: PlayerId

class RosterEntryModel(BaseModel):
    player: Player
    pending: bool