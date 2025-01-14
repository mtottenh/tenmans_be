from pydantic import BaseModel, UUID4, ConfigDict, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# Audit Schemas
class AuditLogCreate(BaseModel):
    action_type: str
    entity_type: str
    entity_id: UUID4
    details: Dict[str, Any]

class AuditLogBase(BaseModel):
    id: UUID4
    action_type: str
    entity_type: str
    entity_id: UUID4
    actor_id: UUID4
    details: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AuditLogDetailed(AuditLogBase):
    actor: "PlayerPublic"  # from auth schemas
    entity_snapshot: Dict[str, Any]  # Snapshot of entity at time of action
