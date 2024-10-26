from pydantic import BaseModel
import uuid
from datetime import datetime

class PlayerModel(BaseModel):
    uid: uuid.UUID
    name: str
    SteamID: str
    created_at: datetime
    update_at: datetime


class PlayerCreateModel(BaseModel):
    uid: uuid.UUID
    name: str
    SteamID: str

class PlayerUpdateModel(BaseModel):
    name: str
    SteamID: str