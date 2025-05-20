import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlmodel import Column, Field, Relationship, SQLModel
from db.models import created_at_field, updated_at_field, timestamp_column
from .schemas import JoinRequestStatus


if TYPE_CHECKING:
    from auth.models import Player
    from competitions.models.seasons import Season
    from teams.models import Team



class TeamJoinRequest(SQLModel, AsyncAttrs, table=True):
    """Model for tracking player requests to join teams"""

    __tablename__ = "team_join_requests"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    player_id: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    season_id: uuid.UUID = Field(sa_column=Column(ForeignKey("seasons.id")))

    # Request details
    message: Optional[str] = Field(default=None)  # Player's message to team
    status: JoinRequestStatus = Field(default=JoinRequestStatus.PENDING)

    # Request workflow timestamps
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    responded_at: Optional[datetime] = Field(sa_column=timestamp_column(nullable=True))

    # Response details
    response_message: Optional[str] = None  # Team's response message
    responded_by: Optional[uuid.UUID] = Field(
        default=None, sa_column=Column(ForeignKey("players.id"))
    )

    # Relationships
    player: "Player" = Relationship(
        back_populates="join_requests",
        sa_relationship_kwargs={"foreign_keys": "TeamJoinRequest.player_id"},
    )
    team: "Team" = Relationship(back_populates="join_requests")
    season: "Season" = Relationship(back_populates="join_requests")
    responder: Optional["Player"] = Relationship(
        back_populates="handled_join_requests",
        sa_relationship_kwargs={"foreign_keys": "TeamJoinRequest.responded_by"},
    )
