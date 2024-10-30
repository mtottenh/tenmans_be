from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import Optional
class PlayerModel(BaseModel):
    uid: uuid.UUID
    name: str
    SteamID: str
    password: str
    is_verified: bool
    created_at: datetime
    update_at: datetime


class PlayerCreateModel(BaseModel):
    name: str
    email: str
    SteamID: str
    password: str
    

class PlayerUpdateModel(BaseModel):
    name: Optional[str]
    email: Optional[str]
    SteamID: Optional[str]
    password: Optional[str]
    role: Optional[str]

class PlayerLoginModel(BaseModel):
    email: str
    password: str