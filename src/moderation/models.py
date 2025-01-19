from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy.dialects.sqlite as sl
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from enum import StrEnum
import uuid
from typing import List, Optional

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

class Ban(SQLModel, AsyncAttrs, table=True):
    __tablename__ = "bans"
    id: uuid.UUID = Field(
        sa_column=Column(UUID, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    # Target can be either a player or team
    player_id: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.id"), nullable=True))
    team_id: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("teams.id"), nullable=True))
    
    # Scope of the ban
    scope: BanScope
    scope_id: Optional[uuid.UUID] = Field(default=None)  # ID of match/tournament/season if applicable
    
    reason: str
    evidence: Optional[str]  # URLs or references to evidence
    status: BanStatus = Field(default=BanStatus.ACTIVE)
    
    # Ban period
    start_date: datetime
    end_date: Optional[datetime]  # Null for permanent bans
    
    # Administrative details
    issued_by: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))  # Admin who issued ban
    revoked_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.id")))
    revoke_reason: Optional[str]
    
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    # Relationships
    player: Optional["Player"] = Relationship(
        back_populates="bans",
        sa_relationship_kwargs={"primaryjoin": "Ban.player_id == Player.id"}
    )
    team: Optional["Team"] = Relationship(back_populates="bans")
    admin: "Player" = Relationship(
        back_populates="issued_bans",
        sa_relationship_kwargs={"foreign_keys": "Ban.issued_by"}
    )
    revoking_admin: Optional["Player"] = Relationship(
        back_populates="revoked_bans",
        sa_relationship_kwargs={"foreign_keys": "Ban.revoked_by"}
    )

