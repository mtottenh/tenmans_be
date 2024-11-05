from sqlmodel import SQLModel, Field, Column, Relationship, ForeignKey
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy_utils import UUIDType
from datetime import datetime
import uuid
from enum import StrEnum


class ResultEnum(StrEnum):
    PENDING = 'pending'
    CANCELED = 'cancled'
    DRAW = 'draw'
    WIN_LOSS = 'win_loss'


class Round(SQLModel, table=True):
    __tablename__ = "rounds"
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, primary_key=True, default=uuid.uuid4)
    )
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id"), nullable=False))
    round_number: int = Field(nullable=False)  # Round number within the season
    fixtures: list["Fixture"] = Relationship(back_populates="round", sa_relationship_kwargs={"lazy": "selectin"})

class Fixture(SQLModel, table=True):
    __tablename__ = "fixtures"

    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    team_1: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    team_2: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id")))
    round_id: uuid.UUID = Field(sa_column=Column(ForeignKey("rounds.id"), nullable=False))
    scheduled_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    result: "Result" = Relationship(
        back_populates="fixture", sa_relationship_kwargs={"lazy": "selectin"}
    )
    round: Round = Relationship(back_populates="fixtures", sa_relationship_kwargs={"lazy": "selectin"})

class Result(SQLModel, table=True):
    __tablename__ = "results"
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, primary_key=True, default=uuid.uuid4)
    )
    fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
    score_team_1: int = Field(default=0)
    score_team_2: int = Field(default=0)
    fixture: Fixture = Relationship(back_populates="result", sa_relationship_kwargs={"lazy": "selectin"})
