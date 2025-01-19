from datetime import datetime
from typing import Dict, Optional
from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSON
import uuid

class EntityStatusHistory(SQLModel, table=True):
    """Generic status history for any entity type"""
    __tablename__ = "entity_status_history"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    entity_type: str  # e.g., "Player", "Team", "Tournament"
    entity_id: uuid.UUID
    previous_status: Optional[str]
    new_status: str
    reason: str
    changed_by: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    entity_metadata: Optional[Dict] = Field(sa_column=Column(JSON))
    
    # Relationship to actor
    actor: "Player" = Relationship(back_populates="status_changes_made")
    
    # Add constraints for valid entity types
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('Player', 'Team', 'Tournament', 'Fixture', 'Season', "
            "'JoinRequest', 'Roster', 'Result', 'Ban', 'Ticket')"
        ),
    )

# Function to create history entries
def create_status_history(
    entity_type: str,
    entity_id: uuid.UUID,
    previous_status: Optional[str],
    new_status: str,
    reason: str,
    changed_by: uuid.UUID,
    entity_metadata: Optional[Dict] = None
) -> EntityStatusHistory:
    """Factory function to create status history entries"""
    return EntityStatusHistory(
        entity_type=entity_type,
        entity_id=entity_id,
        previous_status=previous_status,
        new_status=new_status,
        reason=reason,
        changed_by=changed_by,
        entity_metadata=entity_metadata
    )