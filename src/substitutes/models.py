from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from datetime import datetime
from typing import List, Optional
import uuid

from substitutes.schemas import SubstituteAvailabilityStatus


class SubstituteAvailability(SQLModel, AsyncAttrs, table=True):
    __tablename__ = "substitute_availability"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4))
    player_id: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))
    tournament_id: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("tournaments.id")))
    season_id: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("seasons.id")))
    status: SubstituteAvailabilityStatus = Field(default=SubstituteAvailabilityStatus.AVAILABLE) 
    availability_notes: Optional[str]  # e.g., "Only available weekends"
    last_substitute_date: Optional[datetime]  # Track last time used as substitute
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))

    # Relationships
    player: "Player" = Relationship(back_populates="substitute_availability")
    tournament: Optional["Tournament"] = Relationship(back_populates="substitutes")
    season: Optional["Season"] = Relationship(back_populates="substitutes")
