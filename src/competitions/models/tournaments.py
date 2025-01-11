from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from enum import StrEnum
from typing import List


class TournamentType(StrEnum):
    REGULAR = "regular"
    KNOCKOUT = "knockout"
    PUG = "pug"

class TournamentState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Tournament(SQLModel, table=True):
    __tablename__ = "tournaments"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id")))
    name: str
    type: TournamentType = Field(sa_column=sa.Column(sa.Enum(TournamentType)))
    state: TournamentState = Field(sa_column=sa.Column(sa.Enum(TournamentState)))
    max_team_size: int
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    season: Season = Relationship(back_populates="tournaments")
    rounds: List["Round"] = Relationship(back_populates="tournament")
    fixtures: List["Fixture"] = Relationship(back_populates="tournament")
    maps: List["Map"] = Relationship(back_populates="tournaments", link_model="TournamentMap")
