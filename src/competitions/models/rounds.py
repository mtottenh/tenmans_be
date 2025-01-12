from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from enum import StrEnum
from typing import List
import uuid
class Round(SQLModel, table=True):
    __tablename__ = "rounds"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4))
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    round_number: int
    type: str  # group_stage, knockout, etc.
    best_of: int  # Number of maps in series
    start_date: datetime
    end_date: datetime
    status: str = Field(default="pending")  # pending, active, completed
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    tournament: "Tournament" = Relationship(back_populates="rounds")
    fixtures: List["Fixture"] = Relationship(back_populates="round")
