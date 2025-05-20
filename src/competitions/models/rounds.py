import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlmodel import Column, Field, Relationship, SQLModel
from db.models import created_at_field, updated_at_field, timestamp_column

if TYPE_CHECKING:
    from competitions.models.fixtures import Fixture
    from competitions.models.tournaments import Tournament



class RoundType(StrEnum):
    GROUP_STAGE = "group"
    KNOCKOUT = "knockout"


class Round(SQLModel, AsyncAttrs, table=True):
    __tablename__ = "rounds"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    round_number: int
    type: RoundType  # group_stage, knockout, etc.
    best_of: int  # Number of maps in series
    start_date: datetime = Field(sa_column=timestamp_column())
    end_date: datetime = Field(sa_column=timestamp_column())
    status: str = Field(default="pending")  # pending, active, completed
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    tournament: "Tournament" = Relationship(back_populates="rounds")
    fixtures: list["Fixture"] = Relationship(back_populates="round")
