from sqlmodel import SQLModel, Field, Column, Relationship, ForeignKey
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
import uuid
from enum import StrEnum
from typing import List, Literal


class RoundType(StrEnum):
    GROUP_STAGE = "Group Stage"
    KNOCKOUT = "Knockout"

class Round(SQLModel, table=True):
    __tablename__ = "rounds"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), primary_key=True, default=uuid.uuid4)
    )
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id"), nullable=False))
    round_number: int = Field(nullable=False)  # Round number within the season
    type : RoundType =Field(sa_column=sa.Column(sa.Enum(RoundType)))
    fixtures: list["Fixture"] = Relationship(back_populates="round", sa_relationship_kwargs={"lazy": "selectin"})

class Fixture(SQLModel, table=True):
    __tablename__ = "fixtures"

    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    team_1: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    team_2: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id")))
    round_id: uuid.UUID = Field(sa_column=Column(ForeignKey("rounds.id")))
    scheduled_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    result: "Result" = Relationship(
        back_populates="fixture", sa_relationship_kwargs={"lazy": "selectin"}
    )
    round: Round = Relationship(back_populates="fixtures", sa_relationship_kwargs={"lazy": "selectin"})

class Result(SQLModel, table=True):
    __tablename__ = "results"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), primary_key=True, default=uuid.uuid4)
    )
    fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
    score_team_1: int = Field(default=0)
    score_team_2: int = Field(default=0)
    confirmed: bool = Field(default=False)
    submitted_by: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    fixture: Fixture = Relationship(back_populates="result", sa_relationship_kwargs={"lazy": "selectin"})


class Pug(SQLModel, table=True):
    __tablename__ = "pugs"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    team_1: str
    team_2: str
    map_pool: str
    match_format: str
    # TODO: Can we do things like List[str] and Literal['bo1'] | Literal['bo3']
    pug_result: "PugResult" = Relationship(
        back_populates="pug", sa_relationship_kwargs={"lazy": "selectin"}
    )

class PugResult(SQLModel, table=True):
    __tablename__ = "pug_results"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), primary_key=True, default=uuid.uuid4)
    )
    pug_id: uuid.UUID = Field(sa_column=Column(ForeignKey("pugs.id")))
    score_team_1: int = Field(default=0)
    score_team_2: int = Field(default=0)
    pug: Pug = Relationship(back_populates="pug_result", sa_relationship_kwargs={"lazy": "selectin"})
