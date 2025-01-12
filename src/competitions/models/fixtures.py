from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from enum import StrEnum
from typing import List, Optional
import uuid
class FixtureStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FORFEITED = "forfeited"

class Fixture(SQLModel, table=True):
    __tablename__ = "fixtures"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4))
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    round_id: uuid.UUID = Field(sa_column=Column(ForeignKey("rounds.id")))
    team_1: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    team_2: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    match_format: str  # bo1, bo3, bo5
    scheduled_at: datetime
    rescheduled_from: Optional[datetime]
    rescheduled_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.uid")))
    reschedule_reason: Optional[str]
    status: FixtureStatus = Field(sa_column=sa.Column(sa.Enum(FixtureStatus)))
    forfeit_winner: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("teams.id")))
    forfeit_reason: Optional[str]
    admin_notes: Optional[str]
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    tournament: "Tournament" = Relationship(back_populates="fixtures")
    round: "Round" = Relationship(back_populates="fixtures")
    team_1_rel: "Team" = Relationship(
        back_populates="home_fixtures",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_1"}
    )
    team_2_rel: "Team" = Relationship(
        back_populates="away_fixtures",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_2"}
    )
    results: List["Result"] = Relationship(back_populates="fixture")
    match_players: List["MatchPlayer"] = Relationship(back_populates="fixture")
    team_elo_changes: List["TeamELOHistory"] = Relationship(back_populates="fixture")
