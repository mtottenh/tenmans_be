import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlmodel import Column, Field, Relationship, SQLModel


if TYPE_CHECKING:
    from competitions.models.fixtures import Fixture
    from maps.models import Map
    from teams.models import Team



class LobbyPhase(StrEnum):
    WAITING = "waiting"
    VETO = "veto"
    READY = "ready"
    LIVE = "live"


class VetoActionType(StrEnum):
    BAN = "ban"
    PICK = "pick"
    SIDE = "side"


# Only persist the veto session and actions in the database
class MapVetoSession(SQLModel, table=True):
    """Map veto session for a fixture"""

    __tablename__ = "map_veto_sessions"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
    format: str  # "bo1", "bo3", "bo5"
    status: str  # "pending", "in_progress", "completed"
    current_team_id: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("teams.id"), default=None)
    )
    current_action: Optional[VetoActionType] = Field(default=None)
    deadline: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    completed_at: Optional[datetime] = Field(default=None)

    # Relationships
    fixture: "Fixture" = Relationship(back_populates="veto_session")
    actions: list["MapVetoAction"] = Relationship(back_populates="session")
    current_team: Optional["Team"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[MapVetoSession.current_team_id]"}
    )


class MapVetoAction(SQLModel, table=True):
    """Individual veto actions taken during a session"""

    __tablename__ = "map_veto_actions"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    session_id: uuid.UUID = Field(sa_column=Column(ForeignKey("map_veto_sessions.id")))
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    action_type: VetoActionType = Field(sa_column=Column(Enum(VetoActionType)))
    map_id: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("maps.id")), default=None
    )
    side: Optional[str] = Field(default=None)  # "ct", "t"
    timestamp: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    # Relationships
    session: "MapVetoSession" = Relationship(back_populates="actions")
    team: "Team" = Relationship(back_populates="veto_actions")
    map: Optional["Map"] = Relationship()
