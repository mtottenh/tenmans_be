from enum import Enum
from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSON
from sqlalchemy.ext.asyncio import AsyncAttrs
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid

# class AuditLog(SQLModel, AsyncAttrs, table=True):
#     __tablename__ = "audit_logs"
#     id: uuid.UUID = Field(
#         sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
#     )
#     action_type: str  # ban_team, cancel_match, etc.
#     entity_type: str  # team, fixture, player
#     entity_id: uuid.UUID
#     actor_id: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
#     details: Dict[str, Any] = Field(sa_column=Column(JSON))
#     created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

#     actor: "Player" = Relationship(back_populates="audit_logs")



class AuditEventType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    STATUS_CHANGE = "status_change"
    BULK_OPERATION = "bulk_operation"
    CASCADE = "cascade"

class AuditEvent(SQLModel, table=True):
    """Enhanced audit log model supporting cascading and linking"""
    __tablename__ = "audit_events"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    action_type: str
    event_type: AuditEventType
    entity_type: str
    entity_id: uuid.UUID
    actor_id: uuid.UUID = Field(foreign_key="players.uid")
    details: Dict[str, Any] = Field(sa_column=Column(JSON))
#     created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.
    parent_event_id: Optional[uuid.UUID] = Field(foreign_key="audit_events.id", nullable=True)
    root_event_id: Optional[uuid.UUID] = Field(foreign_key="audit_events.id", nullable=True)
    status_from: Optional[str]
    status_to: Optional[str]
    grace_period_end: Optional[datetime]
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Relationships
    actor: "Player" = Relationship(back_populates="audit_events")
    parent_event: Optional["AuditEvent"] = Relationship(
        back_populates="child_events",
        sa_relationship_kwargs={"foreign_keys": "AuditEvent.parent_event_id"}
    )
    child_events: List["AuditEvent"] = Relationship(
        back_populates="parent_event",
        sa_relationship_kwargs={"foreign_keys": "AuditEvent.parent_event_id"}
    )
