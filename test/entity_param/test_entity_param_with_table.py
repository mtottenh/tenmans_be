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
class TestEntityWithTable(SQLModel, table=True):
    """Test entity with table creation"""

    __tablename__ = "test_entity_with_table"

    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str


@pytest_asyncio.fixture
async def ensure_test_table(session: AsyncSession):
    """Ensure the test table exists"""
    # Create the table if it doesn't exist
    from sqlalchemy import text

    await session.execute(
        text(f"DROP TABLE IF EXISTS {TestEntityWithTable.__tablename__} CASCADE")
    )
    await session.execute(
        text(
            f"""
        CREATE TABLE {TestEntityWithTable.__tablename__} (
            id UUID PRIMARY KEY,
            name VARCHAR NOT NULL
        )
        """
        )
    )
    await session.commit()
    yield
    # Clean up
    await session.execute(
        text(f"DROP TABLE IF EXISTS {TestEntityWithTable.__tablename__} CASCADE")
    )
    await session.commit()


class TestServiceWithTable:
    """Test service that uses the table entity"""

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE, entity_type="TestEntityWithTable"
    )
    async def create_entity(
        self,
        name: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> TestEntityWithTable:
        """Create method"""
        entity = TestEntityWithTable(name=name)
        session.add(entity)
        await session.flush()
        return entity

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="TestEntityWithTable"
    )
    async def update_default(
        self,
        first: TestEntityWithTable,
        second: TestEntityWithTable,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> TestEntityWithTable:
        """Update using default (first entity)"""
        first.name = "First Updated"
        second.name = "Second Updated"
        session.add(first)
        session.add(second)
        await session.flush()
        return second

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TestEntityWithTable",
        entity_param="second",
    )
    async def update_second(
        self,
        first: TestEntityWithTable,
        second: TestEntityWithTable,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> TestEntityWithTable:
        """Update using entity_param=second"""
        first.name = "First Updated Again"
        second.name = "Second Updated Again"
        session.add(first)
        session.add(second)
        await session.flush()
        return second


@pytest.mark.asyncio
async def test_entity_param_with_table(
    session: AsyncSession, system_user: Player, ensure_test_table
):
    """Test entity_param with proper table setup"""
    print("\n=== Testing entity_param with table ===")

    service = TestServiceWithTable()

    # Create two entities
    entity1 = await service.create_entity("First", system_user, session)
    entity2 = await service.create_entity("Second", system_user, session)
    await session.commit()

    print(f"Created entity1: {entity1.id}")
    print(f"Created entity2: {entity2.id}")

    # Get initial event count
    stmt = select(AuditEvent)
    result = await session.execute(stmt)
    initial_events = result.scalars().all()
    initial_count = len(initial_events)
    print(f"Initial event count: {initial_count}")

    # Test default behavior (should audit first entity)
    print("\n--- Testing default behavior ---")
    await service.update_default(entity1, entity2, system_user, session)
    await session.commit()

    # Check which entity was audited
    stmt = select(AuditEvent).where(
        AuditEvent.action_type == AuditEventType.UPDATE,
        AuditEvent.entity_type == "TestEntityWithTable",
    )
    result = await session.execute(stmt)
    update_events = result.scalars().all()

    default_events = [e for e in update_events if e.entity_id == entity1.id]
    print(f"UPDATE events for entity1: {len(default_events)}")

    assert len(default_events) >= 1, "Default behavior should audit the first entity"

    # Test entity_param behavior
    print("\n--- Testing entity_param behavior ---")
    await service.update_second(entity1, entity2, system_user, session)
    await session.commit()

    # Check which entity was audited now
    stmt = select(AuditEvent).where(
        AuditEvent.action_type == AuditEventType.UPDATE,
        AuditEvent.entity_type == "TestEntityWithTable",
    )
    result = await session.execute(stmt)
    all_update_events = result.scalars().all()

    second_events = [e for e in all_update_events if e.entity_id == entity2.id]
    print(f"UPDATE events for entity2: {len(second_events)}")

    assert len(second_events) >= 1, (
        "entity_param='second' should audit the second entity"
    )

    print("✓ Test passed!")
