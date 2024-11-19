from enum import StrEnum
from typing import Optional
from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy_utils import UUIDType
from datetime import datetime
import uuid
from src.teams.models import Roster

class PlayerRoles(StrEnum):
    ADMIN = "admin"
    USER = "user"


class Player(SQLModel, table=True):
    __tablename__ = "players"

    uid: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str
    SteamID: str
    email: str
    current_elo: Optional[int]
    highest_elo: Optional[int]
    role: PlayerRoles = Field(sa_column=Column(
        sl.VARCHAR, nullable=False, server_default="user"
    ))
    is_verified: bool = False
    password_hash: str = Field(exclude=True)
    team_links: list[Roster] = Relationship(back_populates="player", sa_relationship_kwargs={"lazy":"selectin"})
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    update_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))

    def __repr__(self):
        return f"<Player {self.name}>"
