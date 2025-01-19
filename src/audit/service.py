from functools import wraps
from typing import Any, Callable, Dict, Optional, Set, TypeVar, Tuple
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession
from audit.models import AuditEvent, AuditEventType
from auth.models import Player
import inspect

from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid
from typing import List

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

    async def add_event(self, event: AuditEvent):
        """Add a child event to the current context"""
        event.parent_event_id = self.parent_event_id
        event.root_event_id = self.root_event_id
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
        self.affected_entities: Set[uuid.UUID] = set()
        self.operation_details: List[Dict[str, Any]] = []

    async def add_operation(self, entity_id: uuid.UUID, details: Dict[str, Any]):
        """Add an operation to the bulk context"""
        self.affected_entities.add(entity_id)
        self.operation_details.append(details)

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

    async def _create_audit_event(
        self,
        session: AsyncSession,
        action_type: str,
        event_type: AuditEventType,
        entity_type: str,
        entity_id: uuid.UUID,
        actor: Player,
        details: Dict[str, Any],
        status_from: Optional[str] = None,
        status_to: Optional[str] = None,
        grace_period: Optional[timedelta] = None
    ) -> AuditEvent:
        """Create and save an audit event"""
        event = AuditEvent(
            action_type=action_type,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor.id,
            details=details,
            status_from=status_from,
            status_to=status_to,
            grace_period_end=datetime.now() + grace_period if grace_period else None
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

    @classmethod
    def audited_transaction(
        cls,
        action_type: str,
        entity_type: str,
        details_extractor: Optional[Callable] = None,
        id_extractor: Optional[Callable] = None,
        status_field: Optional[str] = None,
        grace_period: Optional[timedelta] = None
    ):
        """Enhanced decorator for auditing create/update transactions"""
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def wrapper(self, *args, **kwargs) -> T:
                audit_service = cls()
                session, actor = cls._get_session_and_actor(args, kwargs, func)
                
                if not session or not actor:
                    raise ValueError("audited_transaction requires session and actor parameters")
                
                try:
                    # Get original status if tracking status changes
                    original_status = None
                    if status_field and args:
                        entity = next((arg for arg in args if hasattr(arg, status_field)), None)
                        if entity:
                            original_status = getattr(entity, status_field)

                    # Execute the wrapped function
                    result = await func(self, *args, **kwargs)
                    
                    # First phase: Commit the main resource
                    await session.commit()
                    
                    # Refresh to get generated IDs
                    if hasattr(result, '__table__'):
                        await session.refresh(result)
                    
                    # Extract entity ID and details
                    entity_id = getattr(result, 'id', None)
                    if id_extractor and entity_id is None:
                        entity_id = id_extractor(self, result)

                    if details_extractor:
                        details = details_extractor(self, result)
                    else:
                        details = {
                            "result_type": type(result).__name__,
                            "result_str": str(result)
                        }

                    # Check for status change
                    new_status = None
                    if status_field and hasattr(result, status_field):
                        new_status = getattr(result, status_field)

                    # Determine event type
                    event_type = AuditEventType.CREATE if not original_status else AuditEventType.UPDATE
                    if original_status and new_status and original_status != new_status:
                        event_type = AuditEventType.STATUS_CHANGE
                    await session.refresh(actor)
                    # Create audit event
                    await audit_service._create_audit_event(
                        session=session,
                        action_type=action_type,
                        event_type=event_type,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        actor=actor,
                        details=details,
                        status_from=original_status,
                        status_to=new_status,
                        grace_period=grace_period
                    )
                    
                    if hasattr(result, '__table__'):
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
        action_type: str,
        entity_type: str,
        details_extractor: Optional[Callable] = None,
        id_extractor: Optional[Callable] = None,
        grace_period: Optional[timedelta] = None
    ):
        """Enhanced decorator for auditing delete transactions"""
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def wrapper(self, *args, **kwargs) -> T:
                audit_service = cls()
                session, actor = cls._get_session_and_actor(args, kwargs, func)
                
                if not session or not actor:
                    raise ValueError("audited_deletion requires session and actor parameters")
                
                try:
                    # Extract details before deletion
                    entity = next((arg for arg in args if hasattr(arg, '__table__')), None)
                    if not entity:
                        raise ValueError("audited_deletion requires an entity to delete")
                    
                    entity_id = getattr(entity, 'id', None)
                    if id_extractor and entity_id is None:
                        entity_id = id_extractor(self, entity)

                    if details_extractor:
                        details = details_extractor(self, entity)
                    else:
                        details = {
                            "entity_type": type(entity).__name__,
                            "entity_str": str(entity)
                        }

                    # Execute the deletion
                    result = await func(self, *args, **kwargs)
                    await session.commit()
                    
                    # Create audit event
                    await audit_service._create_audit_event(
                        session=session,
                        action_type=action_type,
                        event_type=AuditEventType.DELETE,
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

    async def create_bulk_audit_event(
        self,
        context: BulkAuditContext
    ) -> AuditEvent:
        """Create an audit event for a bulk operation"""
        bulk_details = {
            "affected_entities": list(context.affected_entities),
            "operation_count": len(context.operation_details),
            "operations": context.operation_details
        }
        
        return await self._create_audit_event(
            session=context.session,
            action_type=context.action_type,
            event_type=AuditEventType.BULK_OPERATION,
            entity_type=context.entity_type,
            entity_id=uuid.uuid4(),  # Generate a new ID for the bulk operation
            actor=context.actor,
            details=bulk_details
        )

    async def get_audit_trail(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        session: AsyncSession,
        include_cascaded: bool = False,
    ) -> List[AuditEvent]:
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
                ).order_by(desc(AuditEvent.created_at))
                related_events = (await session.execute(stmt)).scalars().all()
                all_events.extend(related_events)
            
            return all_events
        else:
            stmt = select(AuditEvent).where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id
            ).order_by(desc(AuditEvent.created_at))
            return (await session.execute(stmt)).scalars().all()

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



def create_audit_service() -> AuditService:
    return AuditService()