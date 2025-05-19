import pytest
import pytest_asyncio
from uuid import uuid4
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, Field, select
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID
import logging

from audit.service import AuditService
from audit.models import AuditEvent
from audit.schemas import AuditEventType
from audit.context import AuditContext
from auth.models import Player

# Enable ALL debug logging
logging.basicConfig(level=logging.DEBUG)
audit_logger = logging.getLogger('uvicorn.error')
audit_logger.setLevel(logging.DEBUG)


# Simple test entity
class SimpleTestEntity(SQLModel, table=True):
    """Simple test entity"""
    __tablename__ = "simple_test_entities"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str


@pytest_asyncio.fixture
async def create_simple_table(session: AsyncSession):
    """Create the simple test table"""
    from sqlalchemy import text
    await session.execute(text(f"DROP TABLE IF EXISTS {SimpleTestEntity.__tablename__} CASCADE"))
    await session.execute(text(
        f"""
        CREATE TABLE {SimpleTestEntity.__tablename__} (
            id UUID PRIMARY KEY,
            name VARCHAR NOT NULL
        )
        """
    ))
    await session.commit()
    yield
    await session.execute(text(f"DROP TABLE IF EXISTS {SimpleTestEntity.__tablename__} CASCADE"))
    await session.commit()


@pytest.mark.asyncio
async def test_audit_decorator_flow(
    session: AsyncSession,
    system_user: Player,
    create_simple_table
):
    """Debug the audit decorator flow step by step"""
    print("\n=== Debug Audit Decorator Flow ===")
    
    # Create a simple entity first
    entity = SimpleTestEntity(name="Test")
    session.add(entity)
    await session.commit()
    await session.refresh(entity)
    print(f"Created entity: {entity.id}")
    
    # Define a simple service
    class SimpleService:
        @AuditService.audited_transaction(
            action_type=AuditEventType.UPDATE,
            entity_type="TestEntity"  # Use allowed entity type
        )
        async def update_entity(
            self,
            entity: SimpleTestEntity,
            actor: Player,
            session: AsyncSession,
            audit_context: Optional[AuditContext] = None
        ) -> SimpleTestEntity:
            print(f"Inside update_entity: entity={entity.id}, actor={actor.id}")
            print(f"audit_context from params: {audit_context}")
            entity.name = "Updated"
            session.add(entity)
            await session.flush()
            return entity
    
    service = SimpleService()
    
    # Check initial audit events
    stmt = select(AuditEvent)
    result = await session.execute(stmt)
    initial_events = result.scalars().all()
    print(f"Initial audit events: {len(initial_events)}")
    
    # Call the update method
    print("\nCalling update method...")
    try:
        result = await service.update_entity(entity, system_user, session)
        print(f"Update returned: {result.id}")
        await session.commit()
        print("Committed successfully")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    # Check final audit events
    stmt = select(AuditEvent)
    result = await session.execute(stmt)
    final_events = result.scalars().all()
    print(f"Final audit events: {len(final_events)}")
    
    new_events = len(final_events) - len(initial_events)
    print(f"New events created: {new_events}")
    
    if new_events == 0:
        print("No new events created!")
        print("Checking AuditContext status...")
        
        # Let's manually test the flow
        print("\n=== Manual AuditContext Test ===")
        async with AuditContext(session, entity_id=entity.id) as ctx:
            print(f"Created AuditContext: {ctx}")
            await ctx.create_root_event(
                AuditEventType.UPDATE,
                "TestEntity",
                system_user,
                "Manual test"
            )
            print("Created root event")
            
            await ctx.create_audit_event(
                session=session,
                action_type=AuditEventType.UPDATE,
                entity_type="TestEntity",
                entity_id=entity.id,
                actor=system_user,
                details={"manual": "test"}
            )
            print("Created audit event")
        
        # Check again
        stmt = select(AuditEvent)
        result = await session.execute(stmt)
        manual_events = result.scalars().all()
        print(f"Events after manual creation: {len(manual_events)}")
    
    assert new_events > 0, f"Expected audit events, but got {new_events}"