from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy import ForeignKey
from sqlalchemy_utils import UUIDType
from datetime import datetime
import uuid


class Team(SQLModel, table=True):
    __tablename__ = "teams"

    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True)
    logo: str = Field(nullable=True)
    player_links: list['Roster'] = Relationship(
        back_populates="team", sa_relationship_kwargs={"lazy": "selectin"}
    )
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    update_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))


class Roster(SQLModel, table=True):
    __tablename__ = "rosters"
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey('teams.id'), primary_key=True))
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey('players.uid'), primary_key=True))
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey('seasons.id'), primary_key=True))
    pending: bool 
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    update_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    team: Team = Relationship(
        back_populates="player_links", 
    )
    player: "Player" = Relationship( back_populates="team_links")

class TeamCaptain(SQLModel, table=True):
    __tablename__ = "captains"
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey('teams.id'), primary_key=True))
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey('players.uid'), primary_key=True))
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))


