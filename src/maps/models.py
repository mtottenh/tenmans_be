# maps/models.py (updated)

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP, UUID
from sqlmodel import Column, Field, Relationship, SQLModel

from competitions.base_schemas import GameMode, MapCategory
from competitions.map_pool.models import MapPoolMap
from pugs.models import PugMapResult


if TYPE_CHECKING:
    from competitions.map_pool.models import MapPoolVote, TournamentMapPool
    from competitions.models.tournaments import Tournament
    from matches.models import Result



class TournamentMap(SQLModel, table=True):
    __tablename__ = "tournament_maps"
    tournament_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tournaments.id"), primary_key=True)
    )
    map_id: uuid.UUID = Field(sa_column=Column(ForeignKey("maps.id"), primary_key=True))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))


class Map(SQLModel, table=True):
    __tablename__ = "maps"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    name: str = Field(unique=True)
    img: Optional[str]
    category: MapCategory = Field(
        sa_column=sa.Column(sa.Enum(MapCategory)), default=MapCategory.COMPETITIVE
    )
    supported_modes: list[GameMode] = Field(
        sa_column=Column(ARRAY(sa.String)), default=[GameMode.COMPETITIVE_5V5]
    )
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    # Relationships
    tournaments: list["Tournament"] = Relationship(
        back_populates="maps", link_model=TournamentMap
    )
    results: list["Result"] = Relationship(back_populates="map")
    pug_results: list[PugMapResult] = Relationship(back_populates="map")
    map_pools: list["TournamentMapPool"] = Relationship(
        back_populates="maps", link_model=MapPoolMap
    )
    votes: list["MapPoolVote"] = Relationship(back_populates="map")
