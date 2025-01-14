from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from typing import List, Optional
from pugs.models import PugMapResult
import uuid

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
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    tournaments: List["Tournament"] = Relationship(
        back_populates="maps",
        link_model=TournamentMap
    )
    results: List["Result"] = Relationship(back_populates="map")
    pug_results: List[PugMapResult] = Relationship(back_populates="map")


