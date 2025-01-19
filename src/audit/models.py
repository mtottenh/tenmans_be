from enum import Enum
from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSON
from sqlalchemy.ext.asyncio import AsyncAttrs
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid

class AuditEventType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    STATUS_CHANGE = "status_change"
    BULK_OPERATION = "bulk_operation"
    CASCADE = "cascade"

# TODO - This is very close to the EventHistory log
# Is it worth attempting to unify the two?
class AuditEvent(SQLModel, table=True):
    """Enhanced audit log model supporting cascading and linking"""
    __tablename__ = "audit_events"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    action_type: str
    event_type: AuditEventType
    entity_type: str
    entity_id: uuid.UUID
    actor_id: uuid.UUID = Field(foreign_key="players.id")
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
    # Parent event (one side of the relationship)
    parent_event: Optional["AuditEvent"] = Relationship(
        back_populates="child_events",
        sa_relationship_kwargs={"foreign_keys": "AuditEvent.parent_event_id"}
    )
    
    # Child events (many side of the relationship)
    child_events: List["AuditEvent"] = Relationship(
        back_populates="parent_event",
        sa_relationship_kwargs={
            "foreign_keys": "AuditEvent.parent_event_id",
            "remote_side": "AuditEvent.id"  # Define remote side here
        }
    )
    # Add constraints for valid entity types
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('Player', 'Team', 'Tournament', 'Fixture', 'Season', "
            "'JoinRequest', 'Roster', 'Result', 'Ban', 'Ticket')"
        ),
    )
