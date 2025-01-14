from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from enum import StrEnum
from typing import List, Optional
import uuid

from maps.models import TournamentMap


class TournamentType(StrEnum):
    REGULAR = "regular"
    KNOCKOUT = "knockout"
    PUG = "pug"

class TournamentState(StrEnum):
    NOT_STARTED = "not_started"
    REGISTRATION_OPEN = "registration_open"
    REGISTRATION_CLOSED = "registration_closed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Tournament(SQLModel, table=True):
    __tablename__ = "tournaments"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id")))
    name: str
    type: TournamentType = Field(sa_column=sa.Column(sa.Enum(TournamentType)))
    state: TournamentState = Field(sa_column=sa.Column(sa.Enum(TournamentState)))
    
    # Team limits
    min_teams: int = Field(ge=2, default=2)
    max_teams: int = Field(ge=2, default=16)
    max_team_size: int = Field(ge=5, le=10)
    min_team_size: int = Field(ge=5, le=10, default=5)
    
    # Registration period
    registration_start: datetime
    registration_end: datetime
    late_registration_end: Optional[datetime] = None
    allow_late_registration: bool = Field(default=False)
    
    # Tournament configuration
    format_config: dict = Field(default={}, sa_column=Column(sa.JSON))
    seeding_config: dict = Field(default={}, sa_column=Column(sa.JSON))
    map_pool: List[uuid.UUID] = Field(sa_column=Column(sa.JSON))
    
    # Dates
    scheduled_start_date: datetime
    scheduled_end_date: datetime
    actual_start_date: Optional[datetime] = None
    actual_end_date: Optional[datetime] = None
    
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    # Relationships
    season: "Season" = Relationship(back_populates="tournaments")
    rounds: List["Round"] = Relationship(back_populates="tournament")
    fixtures: List["Fixture"] = Relationship(back_populates="tournament")
    maps: List["Map"] = Relationship(
        back_populates="tournaments",
        link_model=TournamentMap
    )
    registrations: List["TournamentRegistration"] = Relationship(back_populates="tournament")
    substitutes: List["SubstituteAvailability"] = Relationship(back_populates="tournament")

class RegistrationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    DISQUALIFIED = "disqualified"

class TournamentRegistration(SQLModel, table=True):
    __tablename__ = "tournament_registrations"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    status: RegistrationStatus = Field(sa_column=sa.Column(sa.Enum(RegistrationStatus)))
    
    # Registration workflow fields
    requested_by: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    requested_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    reviewed_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.uid")))
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    
    # Withdrawal fields
    withdrawn_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.uid")))
    withdrawn_at: Optional[datetime]
    withdrawal_reason: Optional[str]
    
    # Tournament specific fields
    seed: Optional[int]  # For tournament seeding
    group: Optional[str]  # For group stage assignments
    final_position: Optional[int]  # Final tournament position
    
    # Relationships
    tournament: "Tournament" = Relationship(back_populates="registrations")
    team: "Team" = Relationship(back_populates="tournament_registrations")
    requester: "Player" = Relationship(
        sa_relationship_kwargs={"primaryjoin": "TournamentRegistration.requested_by == Player.uid"},
        back_populates="tournament_registration_requests"
    )
    reviewer: Optional["Player"] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "TournamentRegistration.reviewed_by == Player.uid"},
        back_populates="tournament_registration_reviews"
    )