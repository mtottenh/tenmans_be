from typing import Any, Dict, Generic, List, Optional, TypeVar
from datetime import datetime
import uuid
from sqlmodel.ext.asyncio.session import AsyncSession
from audit.service import AuditService
from auth.models import Player
from auth.schemas import PlayerStatus
from auth.service.permission import PermissionService
from status.models import EntityStatusHistory, create_status_history
from .transition_validator import HasRequiredReasonValidator, StatusTransitionManager, StatusTransitionRule, SuspensionDurationValidator
from sqlalchemy.orm import selectinload
from sqlmodel import select
T = TypeVar('T')

class StatusTransitionService(Generic[T]):
    """Service for handling status transitions with audit logging"""
    
    def __init__(self, audit_service: Optional[AuditService] = None, permission_service: Optional[PermissionService] = None):
        self.audit_service = audit_service or AuditService()
        self.permission_service = permission_service or PermissionService()
        self.transition_managers: Dict[str, StatusTransitionManager] = {}
        
    def register_transition_manager(
        self,
        entity_type: str,
        manager: StatusTransitionManager
    ):
        """Register a transition manager for an entity type"""
        self.transition_managers[entity_type] = manager

    def _transition_audit_details(self, entity: Any, context: Dict) -> dict:
        """Extract audit details for status transitions"""
        return {
            "entity_type": type(entity).__name__,
            "entity_id": str(getattr(entity, 'id', None)),
            "previous_status": str(context.get('previous_status')),
            "new_status": str(context.get('new_status')),
            "reason": context.get('reason'),
            "actor_id": str(context['actor'].id),
            "timestamp": datetime.now().isoformat()
        }

    @AuditService.audited_transaction(
        action_type="status_transition",
        entity_type="status",
        details_extractor=_transition_audit_details
    )
    async def transition_status(
        self,
        entity: T,
        new_status: str,
        reason: str,
        actor: Player,
        entity_metadata: Optional[Dict] = None,
        session: AsyncSession = None
    ) -> T:
        """
        Transition an entity's status with validation and history tracking
        
        Args:
            entity: Entity to update
            new_status: New status value
            reason: Reason for the change
            actor: User making the change
            entity_metadata: Additional metadata to store
            session: Database session
        """
        entity_type = type(entity).__name__
        manager = self.transition_managers.get(entity_type)
        if not manager:
            raise ValueError(f"No transition manager registered for {entity_type}")
            
        current_status = entity.status
        new_status_enum = manager.status_enum(new_status)
        
        # Build context for validation
        context = {
            'actor': actor,
            'reason': reason,
            'entity': entity,
            'session': session,
            'permission_service': self.permission_service,
            'entity_metadata': entity_metadata,
            'previous_status': current_status,
            'new_status': new_status_enum
        }
        
        # Validate transition
        await manager.validate_transition(
            current_status,
            new_status_enum,
            context
        )
        
        # Create history entry
        history_entry = create_status_history(
            entity_type=manager.entity_type,
            entity_id=entity.id,
            previous_status=str(current_status),
            new_status=str(new_status_enum),
            reason=reason,
            changed_by=actor.id,
            entity_metadata=entity_metadata
        )
        session.add(history_entry)
        
        # Update entity
        entity.status = new_status_enum
        entity.status_change_reason = reason
        entity.status_changed_at = datetime.now()
        entity.status_changed_by = actor.id
        
        session.add(entity)
        return entity

    async def get_status_history(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        session: AsyncSession,
        include_metadata: bool = False
    ) -> List[Dict]:
        """Get status change history for an entity"""
        stmt = select(EntityStatusHistory).where(
            EntityStatusHistory.entity_type == entity_type,
            EntityStatusHistory.entity_id == entity_id
        ).order_by(EntityStatusHistory.created_at.desc()).options(
            selectinload(EntityStatusHistory.actor)

        )
        
        result = await session.execute(stmt)
        history = result.scalars().all()
        
        return [
            {
                "previous_status": entry.previous_status,
                "new_status": entry.new_status,
                "reason": entry.reason,
                "changed_by": entry.changed_by,
                "created_at": entry.created_at,
                **({"entity_metadata": entry.entity_metadata} if include_metadata else {})
            }
            for entry in history
        ]
    
    async def get_entity_status_changes(
        self,
        entity_type: str,
        session: AsyncSession,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get status changes for all entities of a type within a date range"""
        stmt = select(EntityStatusHistory).where(
            EntityStatusHistory.entity_type == entity_type
        ).options(
            selectinload(EntityStatusHistory.actor)
        )
        
        if from_date:
            stmt = stmt.where(EntityStatusHistory.created_at >= from_date)
        if to_date:
            stmt = stmt.where(EntityStatusHistory.created_at <= to_date)
            
        stmt = stmt.order_by(
            EntityStatusHistory.entity_id,
            EntityStatusHistory.created_at.desc()
        )
        
        result = await session.execute(stmt)
        return result.scalars().all()
