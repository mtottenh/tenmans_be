# maps/models.py (updated)

from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSON, ARRAY
from sqlalchemy import String
import sqlalchemy as sa
from datetime import datetime
from typing import List, Optional
from competitions.map_pool.models import MapPoolMap
from pugs.models import PugMapResult
from sqlalchemy.ext.asyncio import AsyncAttrs
import uuid
from competitions.base_schemas import MapCategory, GameMode


class TournamentMap(SQLModel, table=True):
    __tablename__ = "tournament_maps"
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id"), primary_key=True))
    map_id: uuid.UUID = Field(sa_column=Column(ForeignKey("maps.id"), primary_key=True))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))


class Map(SQLModel, table=True):
    __tablename__ = "maps"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True)
    img: Optional[str]
    category: MapCategory = Field(
        sa_column=sa.Column(sa.Enum(MapCategory)),
        default=MapCategory.COMPETITIVE
    )
    supported_modes: List[GameMode] = Field(
        sa_column=Column(ARRAY(sa.String)),
        default=[GameMode.COMPETITIVE_5V5]
    )
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    # Relationships
    tournaments: List["Tournament"] = Relationship(
        back_populates="maps",
        link_model=TournamentMap
    )
    results: List["Result"] = Relationship(back_populates="map")
    pug_results: List[PugMapResult] = Relationship(back_populates="map")
    map_pools: List["TournamentMapPool"] = Relationship(back_populates="maps", link_model=MapPoolMap)
    votes: List["MapPoolVote"] = Relationship(back_populates="map")