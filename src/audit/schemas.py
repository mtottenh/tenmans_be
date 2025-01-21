from pydantic import BaseModel, UUID4, ConfigDict
from typing import Dict, Any
from datetime import datetime
from enum import StrEnum



# NB - In the database
# Enums take the value of the LHS, so we have to be careful in 
# Prepared statments that do things like create indexes.
class AuditEventType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    STATUS_CHANGE = "status_transition"
    PERMISSION_CHANGE = "permission_change"
    VERIFICATION = "verification"
    BAN = "ban"
    ROLE_CHANGE = "role_change"
    BULK_OPERATION = "bulk_operation"
    CASCADE = "cascade"

class AuditEventState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class ScopeType(StrEnum):
    GLOBAL = "global"
    TEAM = "team"
    TOURNAMENT = "tournament"
    SEASON = "season"


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
