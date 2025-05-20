import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlmodel import Column, Field, Relationship, SQLModel

from db.models import enum_column, created_at_field, updated_at_field


if TYPE_CHECKING:
    from competitions.models.tournaments import Tournament
    from substitutes.models import SubstituteAvailability
    from teams.join_request.models import TeamJoinRequest
    from teams.models import Roster



class SeasonState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Season(SQLModel, table=True):
    __tablename__ = "seasons"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    name: str = Field(unique=True)
    state: SeasonState = Field(sa_column=enum_column(SeasonState))
    created_at: datetime = created_at_field()

    tournaments: list["Tournament"] = Relationship(back_populates="season")
    rosters: list["Roster"] = Relationship(back_populates="season")
    substitutes: list["SubstituteAvailability"] = Relationship(back_populates="season")
    join_requests: list["TeamJoinRequest"] = Relationship(back_populates="season")
