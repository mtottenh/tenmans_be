import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Column, Field, Relationship, SQLModel

from db.models import created_at_field, updated_at_field
from teams.models import Team


if TYPE_CHECKING:
    from auth.models import Player



class BanScope(StrEnum):
    MATCH = "match"
    TOURNAMENT = "tournament"
    SEASON = "season"
    PERMANENT = "permanent"


class BanStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    APPEALED = "appealed"
    REVOKED = "revoked"


class ModerationActionType(StrEnum):
    WARNING = "warning"
    SUSPENSION = "suspension"
    BAN = "ban"
    MUTE = "mute"


class ModerationAction(SQLModel, table=True):
    __tablename__ = "moderation_actions"
    id: uuid.UUID = Field(
        sa_column=Column(UUID, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    player_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("players.id"), nullable=False)
    )
    action_type: ModerationActionType
    reason: str
    scope: str  # global, tournament, season, etc.
    scope_id: Optional[uuid.UUID] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    issued_by: uuid.UUID = Field(
        sa_column=Column(ForeignKey("players.id"))
    )
    active: bool = True
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    # Relationships
    player: "Player" = Relationship(
        back_populates="moderation_actions",
        sa_relationship_kwargs={"primaryjoin": "ModerationAction.player_id == Player.id"},
    )
    admin: "Player" = Relationship(
        back_populates="issued_actions",
        sa_relationship_kwargs={"foreign_keys": "ModerationAction.issued_by"},
    )


class Ban(SQLModel, table=True):
    __tablename__ = "bans"
    id: uuid.UUID = Field(
        sa_column=Column(UUID, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    # Target can be either a player or team
    player_id: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("players.id"), nullable=True)
    )
    team_id: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("teams.id"), nullable=True)
    )

    # Scope of the ban
    scope: BanScope
    scope_id: Optional[uuid.UUID] = Field(
        default=None
    )  # ID of match/tournament/season if applicable

    reason: str
    evidence: Optional[str]  # URLs or references to evidence
    status: BanStatus = Field(default=BanStatus.ACTIVE)

    # Ban period
    start_date: datetime
    end_date: Optional[datetime]  # Null for permanent bans

    # Administrative details
    issued_by: uuid.UUID = Field(
        sa_column=Column(ForeignKey("players.id"))
    )  # Admin who issued ban
    revoked_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.id")))
    revoke_reason: Optional[str]
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    # Relationships
    player: Optional["Player"] = Relationship(
        back_populates="bans",
        sa_relationship_kwargs={"primaryjoin": "Ban.player_id == Player.id"},
    )
    team: Optional[Team] = Relationship(back_populates="bans")
    admin: "Player" = Relationship(
        back_populates="issued_bans",
        sa_relationship_kwargs={"foreign_keys": "Ban.issued_by"},
    )
    revoking_admin: Optional["Player"] = Relationship(
        back_populates="revoked_bans",
        sa_relationship_kwargs={"foreign_keys": "Ban.revoked_by"},
    )
