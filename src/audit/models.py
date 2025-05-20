import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import CheckConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, TIMESTAMP, UUID
from sqlmodel import Column, Field, Index, Relationship, SQLModel

from audit.schemas import AuditEventState, AuditEventType, ScopeType


if TYPE_CHECKING:
    from auth.models import Player



class AuditEvent(SQLModel, table=True):
    """Enhanced audit log model supporting cascading, bulk operations and status tracking"""

    __tablename__ = "audit_events"

    # Base audit fields
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_type: str
    entity_id: Optional[uuid.UUID] = Field(nullable=True)
    action_type: AuditEventType
    actor_id: uuid.UUID = Field(foreign_key="players.id")
    timestamp: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    # Event processing state
    event_state: AuditEventState = Field(default=AuditEventState.PENDING)
    sequence_number: Optional[int]  # For ordering events in a cascade

    # Status transition specific fields
    previous_status: Optional[str]
    new_status: Optional[str]
    transition_reason: Optional[str]

    # Scope information (for permission/role changes)
    scope_type: Optional[ScopeType]
    scope_id: Optional[uuid.UUID]

    # Error tracking
    error_message: Optional[str]
    error_details: Optional[dict[str, Any]] = Field(sa_column=Column(JSON))

    # Bulk operation fields
    affected_entities: Optional[list[uuid.UUID]] = Field(sa_column=Column(ARRAY(UUID)))
    operation_count: Optional[int]

    # Generic details and metadata
    details: dict[str, Any] = Field(sa_column=Column(JSON))

    # Cascade/parent-child relationship fields
    parent_event_id: Optional[uuid.UUID] = Field(
        foreign_key="audit_events.id", nullable=True
    )
    root_event_id: Optional[uuid.UUID] = Field(
        foreign_key="audit_events.id", nullable=True
    )
    grace_period_end: Optional[datetime]

    # Relationships
    actor: "Player" = Relationship(back_populates="audit_events")

    # Parent event (one side of the relationship)
    parent_event: Optional["AuditEvent"] = Relationship(
        back_populates="child_events",
        sa_relationship_kwargs={"foreign_keys": "AuditEvent.parent_event_id"},
    )

    # Child events (many side of the relationship)
    child_events: list["AuditEvent"] = Relationship(
        back_populates="parent_event",
        sa_relationship_kwargs={
            "foreign_keys": "AuditEvent.parent_event_id",
            "remote_side": "AuditEvent.id",
        },
    )

    # Constraints and indexes
    __table_args__ = (
        # Entity type constraint
        CheckConstraint(
            "entity_type IN ('Player', 'Team', 'Tournament', 'Fixture', 'Season', "
            "'TeamJoinRequest', 'TeamCaptain', 'Roster', 'Result', 'Round', 'MatchPlayer', 'TournamentRegistration','Ban', "
            "'Ticket', 'Role', 'PlayerRole', 'Permission', 'status', 'TestParamModel','TestEntityWithTable', 'TestEntity', 'SimpleTestEntity', 'test_entity', 'parent_entity', 'child_entity', 'MockEntity')",
            name="valid_entity_types",
        ),
        # Ensure valid scope types
        CheckConstraint(
            "scope_type IS NULL OR scope_type IN ('GLOBAL', 'TEAM', 'TOURNAMENT', 'SEASON')",
            name="valid_scope_types",
        ),
        # Ensure scope_id is present when scope_type is not global
        CheckConstraint(
            "scope_type = 'GLOBAL' OR (scope_type IS NOT NULL AND scope_id IS NOT NULL)",
            name="valid_scope_id",
        ),
        # Ensure bulk operation fields are present together
        CheckConstraint(
            "(action_type != 'BULK_OPERATION') OR "
            "(action_type = 'BULK_OPERATION' AND affected_entities IS NOT NULL AND operation_count IS NOT NULL)",
            name="valid_bulk_operation",
        ),
        # Indexes for common query patterns
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_action", "action_type"),
        Index("ix_audit_timestamp", "timestamp"),
        Index("ix_audit_root_event", "root_event_id"),
        Index("ix_audit_state", "event_state"),
        Index("ix_audit_actor", "actor_id"),
        Index("ix_audit_scope", "scope_type", "scope_id"),
        # Compound indexes for common queries
        Index(
            "ix_audit_status_transition",
            "entity_type",
            "entity_id",
            "action_type",
            postgresql_where=text("action_type = 'STATUS_CHANGE'"),
        ),
        # Index for cascade queries
        Index(
            "ix_audit_cascade",
            "root_event_id",
            "sequence_number",
            postgresql_where=text("root_event_id IS NOT NULL"),
        ),
        # Index for grace period queries
        Index(
            "ix_audit_grace_period",
            "grace_period_end",
            postgresql_where=text("grace_period_end IS NOT NULL"),
        ),
    )
