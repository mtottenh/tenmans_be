from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSON
from datetime import datetime
from enum import StrEnum
from typing import List, Optional
import uuid

class ConfirmationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"

class Result(SQLModel, table=True):
    __tablename__ = "results"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
    map_id: uuid.UUID = Field(sa_column=Column(ForeignKey("maps.id")))
    map_number: int = Field(default=1)
    team_1_score: int
    team_2_score: int
    team_1_side_first: str  # CT or T
    submitted_by: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    confirmed_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.uid")))
    confirmation_status: ConfirmationStatus = Field(
        sa_column=sa.Column(sa.Enum(ConfirmationStatus)),
        default=ConfirmationStatus.PENDING
    )
    admin_override: bool = Field(default=False)
    admin_override_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.uid")))
    admin_override_reason: Optional[str]
    demo_url: Optional[str]
    screenshot_urls: List[str] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    fixture: "Fixture" = Relationship(back_populates="results")
    map: "Map" = Relationship(back_populates="results")
    submitter: "Player" = Relationship(
        back_populates="submitted_results",
        sa_relationship_kwargs={"foreign_keys": "Result.submitted_by"}
    )
    confirmer: Optional["Player"] = Relationship(
        back_populates="confirmed_results",
        sa_relationship_kwargs={"foreign_keys": "Result.confirmed_by"}
    )
    admin_overrider: Optional["Player"] = Relationship(
        back_populates="admin_overridden_results",
        sa_relationship_kwargs={"foreign_keys": "Result.admin_override_by"}
    )

class MatchPlayer(SQLModel, table=True):
    __tablename__ = "match_players"
    fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id"), primary_key=True))
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid"), primary_key=True))
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    is_substitute: bool = Field(default=False)
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    fixture: "Fixture" = Relationship(back_populates="match_players")
    player: "Player" = Relationship(back_populates="match_participations")
    team: "Team" = Relationship(back_populates="match_players")
