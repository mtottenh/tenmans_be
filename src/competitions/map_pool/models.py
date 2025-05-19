import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlmodel import Column, Field, Relationship, SQLModel


if TYPE_CHECKING:
    from competitions.models.tournaments import Tournament
    from maps.models import Map
    from teams.models import Team



class MapPoolSelectionType(StrEnum):
    ADMIN_DEFINED = "admin_defined"
    TEAM_VOTING = "team_voting"
    PLAYER_VOTING = "player_voting"


class MapPoolStatus(StrEnum):
    VOTING = "voting"  # Only for team voting pools
    FINALIZED = "finalized"  # Pool is set and cannot be changed
    CANCELLED = "cancelled"  # Voting cancelled or pool discarded


class MapPoolMap(SQLModel, table=True):
    """Maps included in a tournament map pool"""

    __tablename__ = "map_pool_maps"

    pool_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tournament_map_pools.id"), primary_key=True)
    )
    map_id: uuid.UUID = Field(sa_column=Column(ForeignKey("maps.id"), primary_key=True))
    vote_count: Optional[int] = Field(default=0)  # For voting pools
    added_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))


class TournamentMapPool(SQLModel, AsyncAttrs, table=True):
    """Represents a tournament's map pool configuration"""

    __tablename__ = "tournament_map_pools"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    selection_type: MapPoolSelectionType
    status: MapPoolStatus

    # Voting configuration (if selection_type is TEAM_VOTING or PLAYER_VOTING)
    voting_start: Optional[datetime] = None
    voting_end: Optional[datetime] = None
    maps_to_select: Optional[int] = None  # Number of maps to include in final pool
    votes_per_team: Optional[int] = None  # Number of votes each team gets

    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    finalized_at: Optional[datetime] = None

    # Relationships
    tournament: "Tournament" = Relationship(back_populates="map_pool")
    maps: list["Map"] = Relationship(back_populates="map_pools", link_model=MapPoolMap)
    team_votes: list["MapPoolVote"] = Relationship(back_populates="map_pool")


class MapPoolVote(SQLModel, AsyncAttrs, table=True):
    """Records votes cast by teams for maps"""

    __tablename__ = "map_pool_votes"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    pool_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournament_map_pools.id")))
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    map_id: uuid.UUID = Field(sa_column=Column(ForeignKey("maps.id")))
    voted_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    # Relationships
    map_pool: TournamentMapPool = Relationship(back_populates="team_votes")
    team: "Team" = Relationship(back_populates="map_votes")
    map: "Map" = Relationship(back_populates="votes")
