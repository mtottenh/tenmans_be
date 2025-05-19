import uuid
from typing import Optional
from uuid import uuid4

import pytest
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, select

from audit.context import AuditContext
from audit.models import AuditEvent
from audit.schemas import AuditEventType
from audit.service import AuditService
from auth.models import Player


# Create test entities that match our constraint
class DebugTestEntity(SQLModel, table=True):
    """Debug test entity"""

    __tablename__ = "debug_test_entities"

    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str


class DebugService:
    """Service to debug entity_param functionality"""

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TestEntity",  # This is allowed in the constraint
    )
    async def update_without_param(
        self,
        first: DebugTestEntity,
        second: DebugTestEntity,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> DebugTestEntity:
        """No entity_param - should audit 'first'"""
        first.name = "Updated First"
        second.name = "Updated Second"
        session.add(first)
        session.add(second)
        await session.flush()
        return second

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TestEntity",  # This is allowed in the constraint
        entity_param="second",  # Should audit 'second'
    )
    async def update_with_param(
        self,
        first: DebugTestEntity,
        second: DebugTestEntity,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> DebugTestEntity:
        """With entity_param - should audit 'second'"""
        first.name = "Updated First Again"
        second.name = "Updated Second Again"
        session.add(first)
        session.add(second)
        await session.flush()
        return second


class TestEntityParamDebug:
    """Debug test for entity_param feature"""

    @pytest.mark.asyncio
    async def test_entity_param_functionality(
        self, session: AsyncSession, system_user: Player
    ):
        """Test that entity_param correctly selects which entity to audit"""
        # Create two entities
        first = DebugTestEntity(name="First")
        second = DebugTestEntity(name="Second")
        session.add(first)
        session.add(second)
        await session.commit()
        await session.refresh(first)
        await session.refresh(second)

        service = DebugService()

        # Test WITHOUT entity_param
        print("\n=== Test WITHOUT entity_param ===")
        await service.update_without_param(
            first, second, system_user, session
        )
        await session.commit()

        # Check all audit events
        stmt = select(AuditEvent).order_by(AuditEvent.timestamp)
        events = await session.execute(stmt)
        all_events = events.scalars().all()

        print(f"Total events after first call: {len(all_events)}")
        for event in all_events:
            print(f"  Event: {event.action_type}, Entity ID: {event.entity_id}")

        # Should have audited 'first'
        first_events = [e for e in all_events if e.entity_id == first.id]
        second_events = [e for e in all_events if e.entity_id == second.id]

        print(f"Events for first entity: {len(first_events)}")
        print(f"Events for second entity: {len(second_events)}")

        assert len(first_events) == 1, "Should have 1 event for first entity"
        assert len(second_events) == 0, "Should have 0 events for second entity"

        # Test WITH entity_param
        print("\n=== Test WITH entity_param ===")
        await service.update_with_param(first, second, system_user, session)
        await session.commit()

        # Check all audit events again
        stmt = select(AuditEvent).order_by(AuditEvent.timestamp)
        events = await session.execute(stmt)
        all_events = events.scalars().all()

        print(f"Total events after second call: {len(all_events)}")
        for event in all_events:
            print(f"  Event: {event.action_type}, Entity ID: {event.entity_id}")

        # Now should have audited 'second'
        first_events = [e for e in all_events if e.entity_id == first.id]
        second_events = [e for e in all_events if e.entity_id == second.id]

        print(f"Events for first entity: {len(first_events)}")
        print(f"Events for second entity: {len(second_events)}")

        assert len(first_events) == 1, "Should still have 1 event for first entity"
        assert len(second_events) == 1, "Should now have 1 event for second entity"
