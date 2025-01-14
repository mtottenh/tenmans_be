from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSON
from datetime import datetime
from enum import StrEnum
from typing import List, Optional
import uuid

from auth.models import Player

class PugStatus(StrEnum):
    CREATING = "creating"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Pug(SQLModel, table=True):
    __tablename__ = "pugs"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    status: PugStatus = Field(
        sa_column=sa.Column(sa.Enum(PugStatus)),
        default=PugStatus.CREATING
    )
    match_format: str  # bo1, bo3
    max_players_per_team: int
    require_full_teams: bool = Field(default=True)
    map_pool: List[uuid.UUID] = Field(sa_column=Column(JSON))  # Array of map IDs
    created_by: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    completed_at: Optional[datetime]

    creator: Player = Relationship(back_populates="created_pugs")
    teams: List["PugTeam"] = Relationship(back_populates="pug")
    players: List["PugPlayer"] = Relationship(back_populates="pug")
    map_results: List["PugMapResult"] = Relationship(back_populates="pug")

class PugTeam(SQLModel, table=True):
    __tablename__ = "pug_teams"
    pug_id: uuid.UUID = Field(sa_column=Column(ForeignKey("pugs.id"), primary_key=True))
    team_number: int = Field(primary_key=True)  # 1 or 2
    team_name: str
    captain_id: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    pug: Pug = Relationship(back_populates="teams")
    captain: "Player" = Relationship(back_populates="pug_captain_of")
    players: List["PugPlayer"] = Relationship(back_populates="team", 
                                               sa_relationship_kwargs={"primaryjoin": "and_(PugPlayer.pug_id == PugTeam.pug_id, foreign(PugPlayer.team_number) == PugTeam.team_number)"}
                                              )

class PugPlayer(SQLModel, table=True):
    __tablename__ = "pug_players"
    pug_id: uuid.UUID = Field(sa_column=Column(ForeignKey("pugs.id"), primary_key=True))
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid"), primary_key=True))
    team_number: Optional[int] = Field(default=None)
    joined_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    pug: Pug = Relationship(back_populates="players")
    player: Player = Relationship(back_populates="pug_participations")
    team: Optional[PugTeam] = Relationship(back_populates="players",
                                            sa_relationship_kwargs={"primaryjoin": "and_(PugPlayer.pug_id == PugTeam.pug_id, foreign(PugPlayer.team_number) == PugTeam.team_number)"}
                                           )

class PugMapResult(SQLModel, table=True):
    __tablename__ = "pug_map_results"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    pug_id: uuid.UUID = Field(sa_column=Column(ForeignKey("pugs.id")))
    map_number: int
    map_id: uuid.UUID = Field(sa_column=Column(ForeignKey("maps.id")))
    team_1_score: int
    team_2_score: int
    team_1_side_first: str  # CT or T
    demo_url: Optional[str]
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    pug: Pug = Relationship(back_populates="map_results")
    map: "Map" = Relationship(back_populates="pug_results")
