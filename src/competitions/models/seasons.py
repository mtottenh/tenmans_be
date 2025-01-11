from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from enum import StrEnum
from typing import List

class SeasonState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class Season(SQLModel, table=True):
    __tablename__ = "seasons"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True)
    state: SeasonState = Field(sa_column=sa.Column(sa.Enum(SeasonState)))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    tournaments: List["Tournament"] = Relationship(back_populates="season")
    rosters: List["Roster"] = Relationship(back_populates="season")
