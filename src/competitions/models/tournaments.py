import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlmodel import Column, Field, Relationship, SQLModel

from competitions.base_schemas import GameMode, LeagueFormat, MapSelectionMethod, TournamentState
from competitions.models.fixtures import Fixture
from competitions.models.rounds import Round
from competitions.models.scheduling import PlayerAvailability, TeamAvailability
from competitions.models.seasons import Season
from db.models import enum_column, created_at_field, updated_at_field, timestamp_column
from maps.models import Map, TournamentMap


if TYPE_CHECKING:
    from auth.models import Player
    from competitions.map_pool.models import TournamentMapPool
    from competitions.models.tournaments import Tournament
    from substitutes.models import SubstituteAvailability
    from teams.models import Team



class TournamentType(StrEnum):
    REGULAR = "regular"
    KNOCKOUT = "knockout"
    PUG = "pug"


class Tournament(SQLModel, table=True):
    __tablename__ = "tournaments"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id")))
    name: str
    type: TournamentType = Field(sa_column=enum_column(TournamentType))
    status: TournamentState = Field(
        sa_column=enum_column(TournamentState)
    )

    # Game mode and league format
    game_mode: GameMode = Field(
        sa_column=enum_column(GameMode),
        default=GameMode.COMPETITIVE_5V5
    )
    league_format: LeagueFormat = Field(
        sa_column=enum_column(LeagueFormat),
        default=LeagueFormat.SINGLE_ROUND_ROBIN,
    )
    map_selection_method: MapSelectionMethod = Field(
        sa_column=enum_column(MapSelectionMethod),
        default=MapSelectionMethod.MAP_VETO,
    )

    # Team limits
    min_teams: int = Field(ge=2, default=2)
    max_teams: int = Field(ge=2, default=16)
    max_team_size: int = Field(ge=5, le=10)
    min_team_size: int = Field(ge=5, le=10, default=5)

    # Registration period
    registration_start: datetime =  Field(sa_column=timestamp_column())
    registration_end: datetime =  Field(sa_column=timestamp_column())
    late_registration_end: Optional[datetime] = Field(sa_column=timestamp_column(nullable=True))
    allow_late_registration: bool = Field(default=False)

    # Tournament configuration
    format_config: dict = Field(default={}, sa_column=Column(sa.JSON))
    seeding_config: dict = Field(default={}, sa_column=Column(sa.JSON))
    scheduling_config: dict = Field(
        default={}, sa_column=Column(sa.JSON)
    )  # For scheduling preferences

    # Dates
    scheduled_start_date: datetime  =  Field(sa_column=timestamp_column())
    scheduled_end_date: datetime =   Field(sa_column=timestamp_column())
    actual_start_date: Optional[datetime] = Field(sa_column=timestamp_column(nullable=True))
    actual_end_date: Optional[datetime] =  Field(sa_column=timestamp_column(nullable=True))

    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    # Relationships
    season: Season = Relationship(back_populates="tournaments")
    rounds: list[Round] = Relationship(back_populates="tournament")
    fixtures: list[Fixture] = Relationship(back_populates="tournament")
    maps: list[Map] = Relationship(
        back_populates="tournaments", link_model=TournamentMap
    )
    registrations: list["TournamentRegistration"] = Relationship(
        back_populates="tournament"
    )
    substitutes: list["SubstituteAvailability"] = Relationship(
        back_populates="tournament"
    )
    map_pool: Optional["TournamentMapPool"] = Relationship(back_populates="tournament")
    player_availability: list["PlayerAvailability"] = Relationship(
        back_populates="tournament"
    )
    team_availability: list["TeamAvailability"] = Relationship(
        back_populates="tournament"
    )


class RegistrationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    DISQUALIFIED = "disqualified"


class TournamentRegistration(SQLModel, table=True):
    __tablename__ = "tournament_registrations"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    status: RegistrationStatus = Field(sa_column=enum_column(RegistrationStatus))

    # Registration workflow fields
    requested_by: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))
    requested_at: datetime =  Field(sa_column=timestamp_column())
    reviewed_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.id")))
    reviewed_at: Optional[datetime] =  Field(sa_column=timestamp_column(nullable=True))
    review_notes: Optional[str]

    # Withdrawal fields
    withdrawn_by: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("players.id"))
    )
    withdrawn_at: Optional[datetime] = Field(sa_column=timestamp_column(nullable=True))
    withdrawal_reason: Optional[str]

    # Tournament specific fields
    seed: Optional[int]  # For tournament seeding
    group: Optional[str]  # For group stage assignments
    final_position: Optional[int]  # Final tournament position

    # Relationships
    tournament: "Tournament" = Relationship(back_populates="registrations")
    team: "Team" = Relationship(back_populates="tournament_registrations")
    requester: "Player" = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "TournamentRegistration.requested_by == Player.id"
        },
        back_populates="tournament_registration_requests",
    )
    reviewer: Optional["Player"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "TournamentRegistration.reviewed_by == Player.id"
        },
        back_populates="tournament_registration_reviews",
    )
