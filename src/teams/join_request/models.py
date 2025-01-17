from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncAttrs
from datetime import datetime
from enum import StrEnum
from typing import Optional
import uuid
from .schemas import JoinRequestStatus


class TeamJoinRequest(SQLModel, AsyncAttrs, table=True):
    """Model for tracking player requests to join teams"""
    __tablename__ = "team_join_requests"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
        )
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id")))
    
    # Request details
    message: Optional[str] = Field(default=None)  # Player's message to team
    status: JoinRequestStatus = Field(default=JoinRequestStatus.PENDING)
    
    # Request workflow timestamps
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    responded_at: Optional[datetime] = None
    
    # Response details
    response_message: Optional[str] = None  # Team's response message
    responded_by: Optional[uuid.UUID] = Field(
        default=None, 
        sa_column=Column(ForeignKey("players.uid"))
    )
    
    # Relationships
    player: "Player" = Relationship(
        back_populates="join_requests",
        sa_relationship_kwargs={"foreign_keys": "TeamJoinRequest.player_uid"}
    )
    team: "Team" = Relationship(back_populates="join_requests")
    season: "Season" = Relationship(back_populates="join_requests")
    responder: Optional["Player"] = Relationship(
        back_populates="handled_join_requests",
        sa_relationship_kwargs={"foreign_keys": "TeamJoinRequest.responded_by"}
    )