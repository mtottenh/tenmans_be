from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy.dialects.sqlite as sl
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy_utils import UUIDType
from datetime import datetime
from enum import StrEnum
from typing import List, Optional



class SubstituteAvailability(SQLModel, table=True):
    __tablename__ = "substitute_availability"
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    tournament_id: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("tournaments.id")))
    season_id: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("seasons.id")))
    is_available: bool = Field(default=True)
    availability_notes: Optional[str]  # e.g., "Only available weekends"
    last_substitute_date: Optional[datetime]  # Track last time used as substitute
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))

    # Relationships
    player: "Player" = Relationship(back_populates="substitute_availability")
    tournament: Optional["Tournament"] = Relationship(back_populates="substitutes")
    season: Optional["Season"] = Relationship(back_populates="substitutes")
