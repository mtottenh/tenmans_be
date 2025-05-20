# competitions/models/scheduling.py

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, JSON, TIMESTAMP, UUID
from sqlmodel import Column, Field, Relationship, SQLModel
from db.models import created_at_field, updated_at_field, timestamp_column

if TYPE_CHECKING:
    from auth.models import Player
    from competitions.models.fixtures import Fixture
    from competitions.models.tournaments import Tournament
    from teams.models import Team



class AvailabilityType(StrEnum):
    """Type of availability"""

    AVAILABLE = "available"
    MAYBE = "maybe"
    UNAVAILABLE = "unavailable"


class AvailabilityStatus(StrEnum):
    """Status of availability entry"""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PlayerAvailability(SQLModel, table=True):
    """Records when players are available for matches"""

    __tablename__ = "player_availability"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    player_id: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))
    tournament_id: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("tournaments.id"))
    )  # Null for general availability
    start_time: datetime = Field(sa_column=timestamp_column())
    end_time: datetime = Field(sa_column=timestamp_column())
    availability_type: AvailabilityType = Field(
        sa_column=Column(Enum(AvailabilityType))
    )
    status: AvailabilityStatus = Field(
        sa_column=Column(Enum(AvailabilityStatus)), default=AvailabilityStatus.ACTIVE
    )
    is_substitute: bool = Field(default=False)
    notes: Optional[str] = None
    recurring: bool = Field(default=False)
    recurring_pattern: Optional[dict] = Field(
        sa_column=Column(JSON), default=None
    )  # For weekly patterns
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    # Relationships
    player: "Player" = Relationship(back_populates="availability")
    tournament: Optional["Tournament"] = Relationship(
        back_populates="player_availability"
    )


class TeamAvailability(SQLModel, table=True):
    """Aggregated availability for a team on a specific date"""

    __tablename__ = "team_availability"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    date: date
    available_players: list[uuid.UUID] = Field(sa_column=Column(ARRAY(UUID)))
    maybe_players: list[uuid.UUID] = Field(sa_column=Column(ARRAY(UUID)))
    unavailable_players: list[uuid.UUID] = Field(sa_column=Column(ARRAY(UUID)))
    available_substitutes: list[uuid.UUID] = Field(sa_column=Column(ARRAY(UUID)))
    has_minimum_players: bool
    updated_at: datetime = updated_at_field()

    # Relationships
    team: "Team" = Relationship(back_populates="availability")
    tournament: "Tournament" = Relationship(back_populates="team_availability")


class ScheduleSuggestion(SQLModel, table=True):
    """Suggested times for fixture scheduling"""

    __tablename__ = "schedule_suggestions"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
    suggested_time: datetime = Field(sa_column=timestamp_column())
    confidence_score: float
    available_players_team1: int
    available_players_team2: int
    conflicts: list[dict] = Field(sa_column=Column(JSON))
    created_at: datetime = created_at_field()

    # Relationships
    fixture: "Fixture" = Relationship(back_populates="schedule_suggestions")


class ScheduleConflict(SQLModel, table=True):
    """Records conflicts for fixture scheduling"""

    __tablename__ = "schedule_conflicts"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
    conflict_type: str  # "player_unavailable", "venue_booked", etc.
    description: str
    severity: str  # "low", "medium", "high"
    affected_players: list[uuid.UUID] = Field(sa_column=Column(ARRAY(UUID)))
    created_at: datetime = created_at_field()

    # Relationships
    fixture: "Fixture" = Relationship(back_populates="schedule_conflicts")
