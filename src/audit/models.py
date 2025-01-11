from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy import ForeignKey
from sqlalchemy_utils import UUIDType
from datetime import datetime
from typing import List, Dict, Any


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    action_type: str  # ban_team, cancel_match, etc.
    entity_type: str  # team, fixture, player
    entity_id: uuid.UUID
    actor_id: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    details: Dict[str, Any] = Field(sa_column=Column(sl.JSON))
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))

    actor: "Player" = Relationship(back_populates="audit_logs")
