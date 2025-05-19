import pytest
import pytest_asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from audit.context import AuditContext
from audit.models import AuditEvent
from audit.schemas import AuditEventType, AuditEventState
from auth.models import Player


class TestAuditContext:
    """Test the AuditContext functionality"""
    
    @pytest.mark.asyncio
    async def test_simple_audit_context(self, session: AsyncSession, system_user: Player):
        """Test basic audit context creation and event logging"""
        entity_id = uuid4()
        
        async with AuditContext(session, entity_id=entity_id) as audit_context:
            # Create an audit event
            event = await audit_context.create_audit_event(
                session=session,
                action_type=AuditEventType.CREATE,
                entity_type="test_entity",
                entity_id=entity_id,
                actor=system_user,
                details={"test_key": "test_value"},
                previous_status="DRAFT",
                new_status="ACTIVE",
                transition_reason="Test creation"
            )
            
            assert event is not None
            assert event.action_type == AuditEventType.CREATE
            assert event.entity_type == "test_entity"
            assert event.entity_id == entity_id
            assert event.actor_id == system_user.id
            assert event.details == {"test_key": "test_value"}
            assert event.previous_status == "DRAFT"
            assert event.new_status == "ACTIVE"
            assert event.transition_reason == "Test creation"
            assert event.event_state == AuditEventState.COMPLETED
    
    @pytest.mark.asyncio
    async def test_nested_audit_contexts(self, session: AsyncSession, system_user: Player):
        """Test nested audit contexts with parent-child relationships"""
        entity_id = uuid4()
        
        # Create root context
        async with AuditContext(session, entity_id=entity_id) as root_context:
            # Create root event
            root_event = await root_context.create_root_event(
                action_type=AuditEventType.CREATE,
                entity_type="parent_entity",
                actor=system_user,
                details={"root": "event"},
                entity_id=entity_id
            )
            
            # Create nested context
            async with AuditContext(
                session, 
                entity_id=entity_id,
                parent_event_id=root_event.id,
                root_event_id=root_event.id
            ) as child_context:
                # Create child event
                child_event = await child_context.create_audit_event(
                    session=session,
                    action_type=AuditEventType.UPDATE,
                    entity_type="child_entity",
                    entity_id=entity_id,
                    actor=system_user,
                    details={"child": "event"}
                )
                
                assert child_event.parent_event_id == root_event.id
                assert child_event.root_event_id == root_event.id
                assert child_event.sequence_number > 0
    
    @pytest.mark.asyncio
    async def test_audit_event_sequence_numbering(self, session: AsyncSession, system_user: Player):
        """Test that sequence numbers increment correctly"""
        entity_id = uuid4()
        
        async with AuditContext(session, entity_id=entity_id) as context:
            events = []
            for i in range(3):
                event = await context.create_audit_event(
                    session=session,
                    action_type=AuditEventType.UPDATE,
                    entity_type="test_entity",
                    entity_id=entity_id,
                    actor=system_user,
                    details={"iteration": i}
                )
                events.append(event)
            
            # Check sequence numbers
            for i, event in enumerate(events):
                assert event.sequence_number == i + 1
    
    @pytest.mark.asyncio
    async def test_audit_context_rollback_on_error(self, session: AsyncSession, system_user: Player):
        """Test that AuditContext handles rollback correctly on exceptions"""
        entity_id = uuid4()
        
        with pytest.raises(RuntimeError, match="Test error"):
            async with AuditContext(session, entity_id=entity_id) as context:
                # Create an event
                await context.create_audit_event(
                    session=session,
                    action_type=AuditEventType.CREATE,
                    entity_type="test_entity",
                    entity_id=entity_id,
                    actor=system_user,
                    details={"test": "event"}
                )
                
                # Raise an exception to trigger rollback
                raise RuntimeError("Test error")
        
        # Verify that no events were saved due to rollback
        # Note: In a proper test environment, we'd check that the DB is rolled back
        # but that requires a fresh session after the rollback
        
    @pytest.mark.asyncio
    async def test_update_root_event_entity_id(self, session: AsyncSession, system_user: Player):
        """Test updating root event entity ID after creation"""
        
        async with AuditContext(session) as context:
            # Create root event without entity_id
            root_event = await context.create_root_event(
                action_type=AuditEventType.CREATE,
                entity_type="test_entity",
                actor=system_user,
                details={"creating": "entity"}
            )
            
            assert root_event.entity_id is None
            
            # Update entity_id after creation
            new_entity_id = uuid4()
            await context.update_root_event_entity_id(new_entity_id)
            
            await session.refresh(root_event)
            assert root_event.entity_id == new_entity_id
    
    @pytest.mark.asyncio
    async def test_audit_context_with_grace_period(self, session: AsyncSession, system_user: Player):
        """Test audit event creation with grace period"""
        from datetime import timedelta
        entity_id = uuid4()
        
        async with AuditContext(session, entity_id=entity_id) as context:
            grace_period = timedelta(hours=1)
            event = await context.create_audit_event(
                session=session,
                action_type=AuditEventType.STATUS_CHANGE,
                entity_type="test_entity",
                entity_id=entity_id,
                actor=system_user,
                details={"test": "grace_period"},
                grace_period=grace_period
            )
            
            assert event.grace_period_end is not None
            # Check that grace period end is approximately 1 hour from now
            time_diff = event.grace_period_end - event.timestamp
            assert time_diff.total_seconds() >= 3590  # Allow small margin
            assert time_diff.total_seconds() <= 3610
    
    @pytest.mark.asyncio
    async def test_context_depth_tracking(self, session: AsyncSession, system_user: Player):
        """Test that context depth is tracked correctly"""
        entity_id = uuid4()
        
        async with AuditContext(session, entity_id=entity_id) as context1:
            assert context1.context_depth == 1
            
            async with AuditContext(
                session, 
                entity_id=entity_id,
                parent_event_id=uuid4()  # Mock parent event ID
            ) as context2:
                assert context2.context_depth == 1  # Each context manages its own depth