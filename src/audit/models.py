from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from typing import List, Dict, Any


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True)), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    action_type: str  # ban_team, cancel_match, etc.
    entity_type: str  # team, fixture, player
    entity_id: uuid.UUID
    actor_id: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    details: Dict[str, Any] = Field(sa_column=Column(sl.JSON))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    actor: "Player" = Relationship(back_populates="audit_logs")
