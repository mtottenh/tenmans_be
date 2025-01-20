from functools import wraps, partial
from typing import Any, Callable, Dict, List, Optional, TypeVar, Tuple
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime, timedelta
import inspect
import uuid
import logging

from auth.models import Player
from audit.models import AuditEvent, AuditEventType, AuditEventState

LOG = logging.getLogger(__name__)
T = TypeVar('T')

class AuditContext:
    """Context manager for tracking cascaded and linked audit events"""
    def __init__(
        self,
        session: AsyncSession,
        parent_event_id: Optional[uuid.UUID] = None,
        root_event_id: Optional[uuid.UUID] = None
    ):
        self.session = session
        self.parent_event_id = parent_event_id
        self.root_event_id = root_event_id or parent_event_id
        self.child_events: List[AuditEvent] = []
        self.sequence_number = 0

    async def add_event(self, event: AuditEvent):
        """Add a child event to the current context"""
        self.sequence_number += 1
        event.parent_event_id = self.parent_event_id
        event.root_event_id = self.root_event_id
        event.sequence_number = self.sequence_number
        self.child_events.append(event)
        self.session.add(event)
        await self.session.flush()

class BulkAuditContext:
    """Context manager for bulk operations"""
    def __init__(
        self,
        session: AsyncSession,
        action_type: str,
        entity_type: str,
        actor: Player
    ):
        self.session = session
        self.action_type = action_type
        self.entity_type = entity_type
        self.actor = actor
        self.affected_entities: List[uuid.UUID] = []
        self.operation_details: List[Dict[str, Any]] = []
        self.error_count = 0
        self.error_details: List[Dict[str, Any]] = []

    async def add_operation(
        self,
        entity_id: uuid.UUID,
        details: Dict[str, Any],
        error: Optional[str] = None
    ):
        """Add an operation to the bulk context"""
        self.affected_entities.append(entity_id)
        self.operation_details.append(details)
        if error:
            self.error_count += 1
            self.error_details.append({
                "entity_id": str(entity_id),
                "error": error,
                **details
            })

class AuditService:
    """Enhanced audit service with support for cascading, bulk operations, and status tracking"""
    
    def __init__(self):
        self._current_context: Optional[AuditContext] = None
        self._bulk_context: Optional[BulkAuditContext] = None

    @staticmethod
    def _get_session_and_actor(args: tuple, kwargs: dict, func: Callable) -> Tuple[Optional[AsyncSession], Optional[Player]]:
        """Extract session and actor from function arguments"""
        session = next((arg for arg in args if isinstance(arg, AsyncSession)), kwargs.get('session'))
        actor = next((arg for arg in args if isinstance(arg, Player)), kwargs.get('actor'))
        
        if not session or not actor:
            sig = inspect.signature(func)
            param_names = list(sig.parameters.keys())
            
            if not session:
                session_idx = param_names.index('session')
                if session_idx < len(args):
                    session = args[session_idx]
            if not actor:
                actor_idx = param_names.index('actor')
                if actor_idx < len(args):
                    actor = args[actor_idx]
                    
        return session, actor
    
    @staticmethod
    def _extract_details(
        details_extractor: Optional[Callable],
        instance: Any,
        result: Any
    ) -> Dict[str, Any]:
        """Extract details using bound or unbound methods"""
        if details_extractor is None:
            return {
                "result_type": type(result).__name__,
                "result_str": str(result)
            }

        if inspect.ismethod(details_extractor):
            # Already bound method
            return details_extractor(result)
        else:
            # Unbound method - bind it to the instance
            bound_method = partial(details_extractor, instance)
            return bound_method(result)

    @staticmethod
    def _extract_id(
        id_extractor: Optional[Callable],
        instance: Any,
        entity: Any
    ) -> uuid.UUID:
        """Extract entity ID using bound or unbound methods"""
        if hasattr(entity, 'id'):
            return entity.id

        if id_extractor is None:
            # Generate a UUID if no ID extractor is provided
            return uuid.uuid4()

        if inspect.ismethod(id_extractor):
            # Already bound method
            return id_extractor(entity)
        else:
            # Unbound method - bind it to the instance
            bound_method = partial(id_extractor, instance)
            return bound_method(entity)

    async def create_audit_event(
        self,
        session: AsyncSession,
        action_type: AuditEventType,
        entity_type: str,
        entity_id: uuid.UUID,
        actor: Player,
        details: Dict[str, Any],
        status_from: Optional[str] = None,
        status_to: Optional[str] = None,
        transition_reason: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[uuid.UUID] = None,
        grace_period: Optional[timedelta] = None
    ) -> AuditEvent:
        """Create and save an audit event"""
        event = AuditEvent(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor.id,
            details=details,
            status_from=status_from,
            status_to=status_to,
            transition_reason=transition_reason,
            scope_type=scope_type,
            scope_id=scope_id,
            grace_period_end=datetime.now() + grace_period if grace_period else None,
            event_state=AuditEventState.COMPLETED
        )
        
        if self._current_context:
            await self._current_context.add_event(event)
        else:
            session.add(event)
            await session.flush()
            
        return event

    def start_audit_context(
        self,
        session: AsyncSession,
        parent_event_id: Optional[uuid.UUID] = None,
        root_event_id: Optional[uuid.UUID] = None
    ) -> AuditContext:
        """Start a new audit context for tracking cascaded changes"""
        context = AuditContext(session, parent_event_id, root_event_id)
        self._current_context = context
        return context

    def start_bulk_context(
        self,
        session: AsyncSession,
        action_type: str,
        entity_type: str,
        actor: Player
    ) -> BulkAuditContext:
        """Start a new bulk operation context"""
        context = BulkAuditContext(session, action_type, entity_type, actor)
        self._bulk_context = context
        return context

    async def create_bulk_audit_event(
        self,
        context: BulkAuditContext
    ) -> AuditEvent:
        """Create an audit event for a bulk operation"""
        event = AuditEvent(
            action_type=AuditEventType.BULK_OPERATION,
            entity_type=context.entity_type,
            entity_id=uuid.uuid4(),  # Generate a new ID for the bulk operation
            actor_id=context.actor.id,
            affected_entities=context.affected_entities,
            operation_count=len(context.operation_details),
            details={
                "operations": context.operation_details,
                "success_count": len(context.operation_details) - context.error_count,
                "error_count": context.error_count,
                "errors": context.error_details if context.error_count > 0 else None
            },
            event_state=AuditEventState.COMPLETED
        )
        
        context.session.add(event)
        await context.session.flush()
        return event

    async def get_audit_trail(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        session: AsyncSession,
        include_cascaded: bool = False,
        include_details: bool = True
    ) -> List[Dict[str, Any]]:
        """Get audit trail for an entity, optionally including cascaded events"""
        if include_cascaded:
            # Get root events for the entity
            stmt = select(AuditEvent).where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
                AuditEvent.parent_event_id.is_(None)
            )
            root_events = (await session.execute(stmt)).scalars().all()
            
            # Get all related events
            all_events = []
            for event in root_events:
                stmt = select(AuditEvent).where(
                    AuditEvent.root_event_id == event.id
                ).order_by(
                    AuditEvent.sequence_number,
                    desc(AuditEvent.timestamp)
                )
                related_events = (await session.execute(stmt)).scalars().all()
                all_events.extend(related_events)
            
            return [
                self._format_audit_event(event, include_details)
                for event in all_events
            ]
        else:
            stmt = select(AuditEvent).where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id
            ).order_by(desc(AuditEvent.timestamp))
            
            events = (await session.execute(stmt)).scalars().all()
            return [
                self._format_audit_event(event, include_details)
                for event in events
            ]

    def _format_audit_event(self, event: AuditEvent, include_details: bool) -> Dict[str, Any]:
        """Format an audit event for response"""
        formatted = {
            "id": event.id,
            "action_type": event.action_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "actor_id": event.actor_id,
            "timestamp": event.timestamp,
            "event_state": event.event_state
        }

        if event.action_type == AuditEventType.STATUS_CHANGE:
            formatted.update({
                "previous_status": event.previous_status,
                "new_status": event.new_status,
                "transition_reason": event.transition_reason
            })

        if event.action_type == AuditEventType.BULK_OPERATION:
            formatted.update({
                "operation_count": event.operation_count,
                "affected_entities": event.affected_entities
            })

        if event.scope_type:
            formatted.update({
                "scope_type": event.scope_type,
                "scope_id": event.scope_id
            })

        if include_details:
            formatted["details"] = event.details
            if event.error_message:
                formatted["error"] = {
                    "message": event.error_message,
                    "details": event.error_details
                }

        return formatted

    async def get_grace_period_events(
        self,
        session: AsyncSession,
        entity_type: Optional[str] = None
    ) -> List[AuditEvent]:
        """Get audit events that are still within their grace period"""
        now = datetime.now()
        stmt = select(AuditEvent).where(
            AuditEvent.grace_period_end.is_not(None),
            AuditEvent.grace_period_end > now
        )
        
        if entity_type:
            stmt = stmt.where(AuditEvent.entity_type == entity_type)
            
        return (await session.execute(stmt)).scalars().all()

    @classmethod
    def audited_transaction(
        cls,
        action_type: AuditEventType,
        entity_type: str,
        details_extractor: Optional[Callable] = None,
        id_extractor: Optional[Callable] = None,
        scope_type: Optional[str] = None,
        grace_period: Optional[timedelta] = None
    ):
        """Decorator for auditing create/update transactions"""
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def wrapper(self, *args, **kwargs) -> T:
                audit_service = cls()
                session, actor = cls._get_session_and_actor(args, kwargs, func)
                
                if not session or not actor:
                    raise ValueError("Session and actor are required for audited transactions")
                
                try:
                    # Execute the wrapped function
                    result = await func(self, *args, **kwargs)
                    await session.flush()
                    await session.refresh(result)
                    await session.refresh(actor)
                    # Extract details and ID
                    details = cls._extract_details(details_extractor, self, result)
                    entity_id = cls._extract_id(id_extractor, self, result)

                    # Create audit event
                    await audit_service.create_audit_event(
                        session=session,
                        action_type=action_type,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        actor=actor,
                        details=details,
                        scope_type=scope_type,
                        scope_id=kwargs.get('scope_id'),
                        grace_period=grace_period
                    )
                    await session.commit()
                    await session.refresh(result)
                    return result
                    
                except Exception as e:
                    await session.rollback()
                    raise
                    
            return wrapper
        return decorator

    @classmethod
    def audited_deletion(
        cls,
        action_type: AuditEventType,
        entity_type: str,
        details_extractor: Optional[Callable] = None,
        id_extractor: Optional[Callable] = None,
        grace_period: Optional[timedelta] = None
    ):
        """Decorator for auditing delete operations"""
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def wrapper(self, *args, **kwargs) -> T:
                audit_service = cls()
                session, actor = cls._get_session_and_actor(args, kwargs, func)
                
                if not session or not actor:
                    raise ValueError("Session and actor are required for audited deletions")
                
                try:
                    # Extract entity before deletion
                    entity = next((arg for arg in args if hasattr(arg, '__table__')), None)
                    if not entity:
                        raise ValueError("Entity required for audited deletion")
                    
                    # Extract details and ID before deletion
                    details = cls._extract_details(details_extractor, self, entity)
                    entity_id = cls._extract_id(id_extractor, self, entity)
                    
                    # Execute the deletion
                    result = await func(self, *args, **kwargs)
                    await session.commit()
                    await session.refresh(actor)
                    # Create audit event
                    await audit_service.create_audit_event(
                        session=session,
                        action_type=AuditEventType.DELETE,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        actor=actor,
                        details=details,
                        grace_period=grace_period
                    )
                    
                    return result
                    
                except Exception as e:
                    await session.rollback()
                    raise
                    
            return wrapper
        return decorator

def create_audit_service() -> AuditService:
    return AuditService()