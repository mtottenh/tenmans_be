import uuid
from typing import Optional
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, select

from audit.context import AuditContext
from audit.models import AuditEvent
from audit.schemas import AuditEventType
from audit.service import AuditService
from auth.models import Player


# Create test entity
class MinimalTestEntity(SQLModel, table=True):
    """Minimal test entity"""

    __tablename__ = "minimal_test_entities"

    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str

    class Config:
        orm_mode = True


@pytest_asyncio.fixture
async def ensure_minimal_table(session: AsyncSession):
    """Ensure the test table exists"""
    from sqlalchemy import text

    await session.execute(
        text(f"DROP TABLE IF EXISTS {MinimalTestEntity.__tablename__} CASCADE")
    )
    await session.execute(
        text(
            f"""
        CREATE TABLE {MinimalTestEntity.__tablename__} (
            id UUID PRIMARY KEY,
            name VARCHAR NOT NULL
        )
        """
        )
    )
    await session.commit()
    yield
    await session.execute(
        text(f"DROP TABLE IF EXISTS {MinimalTestEntity.__tablename__} CASCADE")
    )
    await session.commit()


class MinimalService:
    """Minimal service to test audit"""

    # Simple method with default behavior
    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE, entity_type="TestEntity"
    )
    async def create_entity(
        self,
        name: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> MinimalTestEntity:
        """Create method"""
        entity = MinimalTestEntity(name=name)
        session.add(entity)
        await session.flush()
        print(f"Created entity with ID: {entity.id}")
        return entity

    # Update with entity_param
    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TestEntity",
        entity_param="entity",  # Explicitly specify the entity parameter
    )
    async def update_entity(
        self,
        entity: MinimalTestEntity,
        new_name: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> MinimalTestEntity:
        """Update method with entity_param"""
        print(f"Updating entity {entity.id} from '{entity.name}' to '{new_name}'")
        entity.name = new_name
        session.add(entity)
        await session.flush()
        return entity


class TestEntityParamMinimal:
    """Minimal test for entity_param feature"""

    @pytest.mark.asyncio
    async def test_create_with_audit(
        self, session: AsyncSession, system_user: Player, ensure_minimal_table
    ):
        """Test CREATE audit"""
        print("\n=== Testing CREATE ===")
        service = MinimalService()

        # Create entity
        entity = await service.create_entity("Test Entity", system_user, session)
        await session.commit()

        # Check audit events
        stmt = select(AuditEvent)
        result = await session.execute(stmt)
        events = result.scalars().all()

        print(f"Total audit events: {len(events)}")
        for event in events:
            print(f"  Event: {event.action_type}, entity_id: {event.entity_id}")

        # Find CREATE events
        create_events = [e for e in events if e.action_type == AuditEventType.CREATE]
        assert len(create_events) >= 1, "Should have at least one CREATE event"
        print(f"Found {len(create_events)} CREATE events")

        # Check the event details
        event = create_events[-1]  # Get the most recent
        assert event.entity_type == "TestEntity"
        assert event.entity_id == entity.id
        assert event.actor_id == system_user.id
        print(f"CREATE event found: {event.id}")

    @pytest.mark.asyncio
    async def test_update_with_audit(
        self, session: AsyncSession, system_user: Player, ensure_minimal_table
    ):
        """Test UPDATE audit"""
        print("\n=== Testing UPDATE ===")
        service = MinimalService()

        # Create entity first
        entity = await service.create_entity("Original Name", system_user, session)
        await session.commit()
        await session.refresh(entity)

        # Update entity
        await service.update_entity(
            entity, "Updated Name", system_user, session
        )
        await session.commit()

        # Check audit events
        stmt = select(AuditEvent)
        result = await session.execute(stmt)
        events = result.scalars().all()

        print(f"Total audit events: {len(events)}")

        # Find UPDATE events
        update_events = [e for e in events if e.action_type == AuditEventType.UPDATE]
        assert len(update_events) >= 1, "Should have at least one UPDATE event"
        print(f"Found {len(update_events)} UPDATE events")

        # Check the event details
        event = update_events[-1]  # Get the most recent
        assert event.entity_type == "TestEntity"
        assert event.entity_id == entity.id
        assert event.actor_id == system_user.id
        print(f"UPDATE event found: {event.id}")

    @pytest.mark.asyncio
    async def test_entity_param_selection(
        self, session: AsyncSession, system_user: Player, ensure_minimal_table
    ):
        """Test that entity_param correctly selects which entity to audit"""
        print("\n=== Testing entity_param selection ===")

        # Create a test service with two different methods
        class TestService:
            @AuditService.audited_transaction(
                action_type=AuditEventType.UPDATE,
                entity_type="TestEntity",
                # No entity_param - will use first SQLModel entity
            )
            async def update_default(
                self,
                first: MinimalTestEntity,
                second: MinimalTestEntity,
                actor: Player,
                session: AsyncSession,
                audit_context: Optional[AuditContext] = None,
            ) -> MinimalTestEntity:
                first.name = "First Updated"
                second.name = "Second Updated"
                session.add(first)
                session.add(second)
                await session.flush()
                return second

            @AuditService.audited_transaction(
                action_type=AuditEventType.UPDATE,
                entity_type="TestEntity",
                entity_param="second",  # Should audit the second entity
            )
            async def update_second(
                self,
                first: MinimalTestEntity,
                second: MinimalTestEntity,
                actor: Player,
                session: AsyncSession,
                audit_context: Optional[AuditContext] = None,
            ) -> MinimalTestEntity:
                first.name = "First Updated Again"
                second.name = "Second Updated Again"
                session.add(first)
                session.add(second)
                await session.flush()
                return second

        # Create two entities
        first = MinimalTestEntity(name="First")
        second = MinimalTestEntity(name="Second")
        session.add(first)
        session.add(second)
        await session.commit()
        await session.refresh(first)
        await session.refresh(second)

        service = TestService()

        # Get initial event count
        stmt = select(AuditEvent)
        result = await session.execute(stmt)
        initial_events = result.scalars().all()
        initial_count = len(initial_events)
        print(f"Initial event count: {initial_count}")

        # Test default behavior (should audit first entity)
        await service.update_default(first, second, system_user, session)
        await session.commit()

        # Check which entity was audited
        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.action_type == AuditEventType.UPDATE,
                AuditEvent.entity_type == "TestEntity",
            )
            .order_by(AuditEvent.timestamp)
        )
        result = await session.execute(stmt)
        update_events = result.scalars().all()

        print(f"Events after update_default: {len(update_events)}")
        default_events = [e for e in update_events if e.entity_id == first.id]
        print(f"Events for first entity: {len(default_events)}")

        assert len(default_events) >= 1, (
            "Default behavior should audit the first entity"
        )

        # Test entity_param behavior (should audit second entity)
        await service.update_second(first, second, system_user, session)
        await session.commit()

        # Check which entity was audited now
        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.action_type == AuditEventType.UPDATE,
                AuditEvent.entity_type == "TestEntity",
            )
            .order_by(AuditEvent.timestamp)
        )
        result = await session.execute(stmt)
        all_update_events = result.scalars().all()

        # Count events for each entity
        final_first_events = [e for e in all_update_events if e.entity_id == first.id]
        final_second_events = [e for e in all_update_events if e.entity_id == second.id]

        print(f"Events for first entity: {len(final_first_events)}")
        print(f"Events for second entity: {len(final_second_events)}")

        assert len(final_second_events) >= 1, (
            "entity_param='second' should audit the second entity"
        )

        print("✓ Test passed!")
