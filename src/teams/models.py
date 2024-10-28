from sqlmodel import SQLModel, Field, Column, Relationship
from async_sqlmodel import AsyncSQLModel, AwaitableField
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy_utils import UUIDType
from datetime import datetime
import uuid
from typing import Awaitable


class Settings(SQLModel, table=True):
    __tablename__ = "tenman_settings"
    name: str = Field(primary_key=True)
    value: str


class Season(SQLModel, table=True):
    __tablename__ = "seasons"
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True)
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))


class Roster(SQLModel, table=True):
    __tablename__ = "rosters"
    team_id: uuid.UUID = Field(foreign_key="teams.id", primary_key=True)
    player_uid: uuid.UUID = Field(foreign_key="players.uid", primary_key=True)
    season_id: uuid.UUID = Field(foreign_key="seasons.id", primary_key=True)
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    update_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    team: "Team" = Relationship(
        back_populates="player_links",
    )
    player: "Player" = Relationship(
        back_populates="team_links",
    )


class Team(SQLModel, table=True):
    __tablename__ = "teams"

    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True)
    player_links: list[Roster] = Relationship(
        back_populates="team", sa_relationship_kwargs={"lazy": "selectin"}
    )
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    update_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
