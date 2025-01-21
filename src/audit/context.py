from typing import Any, Dict, Optional, List
import uuid
from audit.models import AuditEvent
from audit.schemas import AuditEventState, AuditEventType
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from auth.models import Player



class AuditContext:
    """Context manager for tracking cascaded and linked audit events"""
    def __init__(
        self,
        session: AsyncSession,
        entity_id: Optional[uuid.UUID] = None,
        parent_event_id: Optional[uuid.UUID] = None,
        root_event_id: Optional[uuid.UUID] = None,
        root_event: Optional[AuditEvent] = None
    ):
        self.session = session
        self.entity_id = entity_id 
        self.parent_event_id = parent_event_id
        self.root_event_id = root_event_id or parent_event_id
        self.child_events: List[AuditEvent] = []
        self.sequence_number = 0
        self.root_event = root_event or None
        self.context_depth = 0
        self._active = False
        self.start_time = datetime.now()

    async def create_audit_event(
        self,
        session: AsyncSession,
        action_type: AuditEventType,
        entity_type: str,
        entity_id: Optional[uuid.UUID],
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
        await session.refresh(actor)
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
        
        return await self.add_event(event)

    async def create_root_event(self, action_type: AuditEventType, 
                                entity_type: str, 
                                actor: str, 
                                details: str,
                                entity_id: Optional[uuid.UUID] = None
                                ):
        """Create the root audit event when entering a new context"""
        if self.root_event is None:
            # If there's no root event yet, create it
            final_entity_id = entity_id or self.entity_id
            root_event = await self.create_audit_event(
                session=self.session,
                action_type=action_type,
                entity_type=entity_type,
                entity_id=entity_id,
                actor=actor,
                details=details,
            )
            self.root_event = root_event
            self.root_event_id = root_event.id

            if final_entity_id is None and entity_id:
                self.root_event.entity_id = entity_id
                self.session.add(self.root_event)
                await self.session.flush()

        return self.root_event
    
    async def update_root_event_entity_id(self, entity_id: uuid.UUID):
        """Update the root event's entity_id after entity creation"""
        await self.session.refresh(self.root_event)
        if self.root_event and self.root_event.entity_id is None and self.context_depth == 1:
            self.root_event.entity_id = entity_id
            self.session.add(self.root_event)
            await self.session.flush()

    async def add_event(self, event: AuditEvent):
        """Add a child event to the current context"""
        self.sequence_number += 1
        event.parent_event_id = self.parent_event_id
        event.root_event_id = self.root_event_id
        event.sequence_number = self.sequence_number
        self.child_events.append(event)
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def __aenter__(self):
        """Enter the context and return the current instance"""
        self.context_depth += 1 
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Exit the context and handle any finalization tasks"""
        self.context_depth -= 1
        if exc_type:
            # Handle rollback if there was an exception
            if self.context_depth == 0:
                await self.session.rollback()
            raise exc_value

        if self.context_depth == 0:
            if self.child_events or self.root_event:
                await self.session.commit()
            await self.session.flush()