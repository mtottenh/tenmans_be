from sqlmodel import SQLModel, Field, Column, Relationship
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


class Fixture(SQLModel, table=True):
    __tablename__ = "fixtures"

    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    team_1: uuid.UUID = Field(foreign_key="teams.id")
    team_2: uuid.UUID = Field(foreign_key="teams.id")
    season_id: uuid.UUID = Field(foreign_key="seasons.id")
    scheduled_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    result: "Result" = Relationship(
        back_populates="fixture", sa_relationship_kwargs={"lazy": "selectin"}
    )


class Result(SQLModel, table=True):
    __tablename__ = "results"
    fixture_id: uuid.UUID = Field(foreign_key="fixtures.id", primary_key=True)
    winning_team: uuid.UUID | None = Field(foreign_key="teams.id")
    result: ResultEnum
    fixture: Fixture = Relationship(
        back_populates="result", sa_relationship_kwargs={"lazy": "selectin"}
    )
