import pytest
import pytest_asyncio
from uuid import uuid4
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, Field, select
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from audit.service import AuditService
from audit.models import AuditEvent
from audit.schemas import AuditEventType
from audit.context import AuditContext
from auth.models import Player


# Create simple test models
class TestParamModel(SQLModel, table=True):
    """A simple model for testing"""
    __tablename__ = "test_param_models"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str
    value: int = Field(default=0)


class TestEntityParamFeature:
    """Test the entity_param feature of AuditService.audited_transaction"""
    
    @pytest.mark.asyncio
    async def test_entity_param_specifies_correct_argument(
        self,
        session: AsyncSession,
        system_user: Player
    ):
        """Test that entity_param correctly identifies which argument to audit"""
        
        # Create test entities
        entity1 = TestParamModel(name="Entity 1", value=1)
        entity2 = TestParamModel(name="Entity 2", value=2)
        session.add(entity1)
        session.add(entity2)
        await session.commit()
        
        # Define a service class with two methods
        class TestService:
            @AuditService.audited_transaction(
                action_type=AuditEventType.UPDATE,
                entity_type="TestParamModel"
                # No entity_param - will use first SQLModel entity
            )
            async def update_without_param(
                self,
                first_entity: TestParamModel,
                second_entity: TestParamModel,
                actor: Player,
                session: AsyncSession,
                audit_context: Optional[AuditContext] = None
            ) -> TestParamModel:
                """Method without entity_param specified"""
                first_entity.value += 10
                second_entity.value += 20
                session.add(first_entity)
                session.add(second_entity)
                await session.flush()
                return second_entity
            
            @AuditService.audited_transaction(
                action_type=AuditEventType.UPDATE,
                entity_type="TestParamModel",
                entity_param="second_entity"  # Explicitly specify second entity
            )
            async def update_with_param(
                self,
                first_entity: TestParamModel,
                second_entity: TestParamModel,
                actor: Player,
                session: AsyncSession,
                audit_context: Optional[AuditContext] = None
            ) -> TestParamModel:
                """Method with entity_param specified"""
                first_entity.value += 10
                second_entity.value += 20
                session.add(first_entity)
                session.add(second_entity)
                await session.flush()
                return second_entity
        
        service = TestService()
        
        # Test 1: Without entity_param (should audit first_entity)
        await service.update_without_param(entity1, entity2, system_user, session)
        
        # Check audit event for entity1
        stmt = select(AuditEvent).where(
            AuditEvent.entity_id == entity1.id,
            AuditEvent.action_type == AuditEventType.UPDATE
        )
        result = await session.execute(stmt)
        entity1_events = result.scalars().all()
        
        assert len(entity1_events) == 1, "Should have 1 audit event for entity1"
        assert entity1_events[0].entity_type == "TestParamModel"
        
        # Check audit event for entity2 (should not have one from this call)
        stmt = select(AuditEvent).where(
            AuditEvent.entity_id == entity2.id,
            AuditEvent.action_type == AuditEventType.UPDATE
        )
        result = await session.execute(stmt)
        entity2_events_before = result.scalars().all()
        
        assert len(entity2_events_before) == 0, "Should have no audit events for entity2 yet"
        
        # Test 2: With entity_param="second_entity" (should audit entity2)
        await service.update_with_param(entity1, entity2, system_user, session)
        
        # Check audit event for entity2
        stmt = select(AuditEvent).where(
            AuditEvent.entity_id == entity2.id,
            AuditEvent.action_type == AuditEventType.UPDATE
        )
        result = await session.execute(stmt)
        entity2_events_after = result.scalars().all()
        
        assert len(entity2_events_after) == 1, "Should now have 1 audit event for entity2"
        assert entity2_events_after[0].entity_type == "TestParamModel"
        
        # entity1 should still only have the one event from before
        stmt = select(AuditEvent).where(
            AuditEvent.entity_id == entity1.id,
            AuditEvent.action_type == AuditEventType.UPDATE
        )
        result = await session.execute(stmt)
        entity1_events_after = result.scalars().all()
        
        assert len(entity1_events_after) == 1, "entity1 should still have just 1 event"
    
    @pytest.mark.asyncio
    async def test_entity_param_with_kwargs(
        self,
        session: AsyncSession,
        system_user: Player
    ):
        """Test that entity_param works with keyword arguments"""
        
        entity = TestParamModel(name="Test Entity", value=42)
        session.add(entity)
        await session.commit()
        
        class TestService:
            @AuditService.audited_transaction(
                action_type=AuditEventType.UPDATE,
                entity_type="TestParamModel",
                entity_param="target"  # Parameter passed as kwarg
            )
            async def update_entity(
                self,
                new_value: int,
                actor: Player,
                session: AsyncSession,
                target: TestParamModel = None  # Entity as keyword argument
            ) -> TestParamModel:
                """Method with entity as keyword argument"""
                if target:
                    target.value = new_value
                    session.add(target)
                    await session.flush()
                return target
        
        service = TestService()
        
        # Call with entity as keyword argument
        await service.update_entity(
            new_value=999,
            actor=system_user,
            session=session,
            target=entity  # Passed as kwarg
        )
        
        # Verify audit event was created
        stmt = select(AuditEvent).where(
            AuditEvent.entity_id == entity.id,
            AuditEvent.action_type == AuditEventType.UPDATE
        )
        result = await session.execute(stmt)
        events = result.scalars().all()
        
        assert len(events) == 1
        assert events[0].entity_type == "TestParamModel"
        assert events[0].entity_id == entity.id