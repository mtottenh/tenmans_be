from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSON
from datetime import datetime
import uuid
from typing import List, Optional

class Team(SQLModel, table=True):
    __tablename__ = "teams"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4))
    name: str = Field(unique=True)
    logo: Optional[str]
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    rosters: List["Roster"] = Relationship(back_populates="team")
    captains: List["TeamCaptain"] = Relationship(back_populates="team")
    elo_history: List["TeamELOHistory"] = Relationship(back_populates="team")
    home_fixtures: List["Fixture"] = Relationship(
        back_populates="team_1_rel",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_1"}
    )
    away_fixtures: List["Fixture"] = Relationship(
        back_populates="team_2_rel",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_2"}
    )
    bans: List["Ban"] = Relationship(back_populates="team")

class Roster(SQLModel, table=True):
    __tablename__ = "rosters"
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id"), primary_key=True))
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid"), primary_key=True))
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id"), primary_key=True))
    pending: bool = Field(default=True)
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    team: Team = Relationship(back_populates="rosters")
    player: "Player" = Relationship(back_populates="team_rosters")
    season: "Season" = Relationship(back_populates="rosters")

class TeamCaptain(SQLModel, table=True):
    __tablename__ = "team_captains"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4))
    
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    team: Team = Relationship(back_populates="captains")
    player: "Player" = Relationship(back_populates="captain_of")

# class TeamELOHistory(SQLModel, table=True):
#     __tablename__ = "team_elo_history"
#     id: uuid.UUID = Field(
#         sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4))
    
#     team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
#     fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
#     elo_rating: int
#     player_composition: List[uuid.UUID] = Field(sa_column=Column(JSON))
#     created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
#     team: Team = Relationship(back_populates="elo_history")
#     fixture: "Fixture" = Relationship(back_populates="team_elo_changes")
