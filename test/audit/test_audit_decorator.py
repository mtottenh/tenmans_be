import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel

from audit.context import AuditContext
from audit.models import AuditEvent
from audit.schemas import AuditEventType
from audit.service import AuditService
from auth.models import Player


# Create test entities
class AuditTestEntity(SQLModel, table=True):
    """A test entity for testing audit decorators"""

    __tablename__ = "test_entities"

    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str
    status: str = Field(default="ACTIVE")
    value: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# Create a test service with decorated methods
class TestEntityService:
    """Test service to verify audit decorator behavior"""

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE, entity_type="AuditTestEntity"
    )
    async def create_entity_default(
        self,
        entity: AuditTestEntity,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> AuditTestEntity:
        """Create method using default behavior (first SQLModel argument)"""
        session.add(entity)
        await session.flush()
        return entity

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="AuditTestEntity",
        entity_param="target_entity",  # Specify which parameter is the entity
    )
    async def update_entity_with_param(
        self,
        some_id: uuid.UUID,  # This comes first
        target_entity: AuditTestEntity,  # But this is the entity we want to audit
        new_value: int,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> AuditTestEntity:
        """Update method with entity_param specified"""
        target_entity.value = new_value
        target_entity.updated_at = datetime.now(timezone.utc)
        session.add(target_entity)
        await session.flush()
        return target_entity

    @AuditService.audited_transaction(
        action_type=AuditEventType.DELETE,
        entity_type="AuditTestEntity",
        entity_param="entity_to_delete",
    )
    async def delete_entity_with_param(
        self,
        reason: str,  # Non-entity parameter comes first
        entity_to_delete: AuditTestEntity,  # Entity specified by entity_param
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> None:
        """Delete method with entity_param specified"""
        entity_to_delete.status = "DELETED"
        session.add(entity_to_delete)
        await session.flush()


class TestAuditDecorator:
    """Test the audit decorator with entity_param feature"""

    @pytest_asyncio.fixture
    async def test_service(self):
        """Create a test service instance"""
        return TestEntityService()

    @pytest_asyncio.fixture
    async def test_entity(self, session: AsyncSession):
        """Create a test entity"""
        entity = AuditTestEntity(name="Test Entity", value=42)
        session.add(entity)
        await session.commit()
        await session.refresh(entity)
        return entity

    @pytest.mark.asyncio
    async def test_create_with_default_behavior(
        self,
        test_service: TestEntityService,
        session: AsyncSession,
        system_user: Player,
    ):
        """Test that default behavior works (first SQLModel argument)"""
        # Create a new entity
        new_entity = AuditTestEntity(name="Created Entity", value=100)

        # Call the decorated method
        result = await test_service.create_entity_default(
            new_entity, system_user, session
        )

        # Verify the entity was created
        assert result.id is not None
        assert result.name == "Created Entity"
        assert result.value == 100

        # Verify audit event was created
        audit_events = await session.execute(
            AuditEvent.__table__.select().where(AuditEvent.entity_id == result.id)
        )
        events = audit_events.fetchall()
        assert len(events) > 0

        # Check the most recent event
        latest_event = max(events, key=lambda e: e.timestamp)
        assert latest_event.action_type == AuditEventType.CREATE
        assert latest_event.entity_type == "AuditTestEntity"
        assert latest_event.entity_id == result.id
        assert latest_event.actor_id == system_user.id

    @pytest.mark.asyncio
    async def test_update_with_entity_param(
        self,
        test_service: TestEntityService,
        test_entity: AuditTestEntity,
        session: AsyncSession,
        system_user: Player,
    ):
        """Test that entity_param correctly identifies the entity"""
        # Update the entity - note that some_id comes first
        result = await test_service.update_entity_with_param(
            uuid4(),  # some_id parameter (not the entity)
            test_entity,  # target_entity parameter (the actual entity)
            999,  # new_value
            system_user,
            session,
        )

        # Verify the update
        assert result.value == 999

        # Verify audit event was created for the correct entity
        audit_events = await session.execute(
            AuditEvent.__table__.select().where(AuditEvent.entity_id == test_entity.id)
        )
        events = audit_events.fetchall()
        assert len(events) > 0

        # Check the most recent event
        latest_event = max(events, key=lambda e: e.timestamp)
        assert latest_event.action_type == AuditEventType.UPDATE
        assert latest_event.entity_type == "AuditTestEntity"
        assert latest_event.entity_id == test_entity.id
        assert latest_event.actor_id == system_user.id

    @pytest.mark.asyncio
    async def test_delete_with_entity_param(
        self,
        test_service: TestEntityService,
        test_entity: AuditTestEntity,
        session: AsyncSession,
        system_user: Player,
    ):
        """Test delete operation with entity_param"""
        # Delete the entity - note that reason comes first
        await test_service.delete_entity_with_param(
            "Test deletion",  # reason parameter (not the entity)
            test_entity,  # entity_to_delete parameter (the actual entity)
            system_user,
            session,
        )

        # Verify the entity was marked as deleted
        await session.refresh(test_entity)
        assert test_entity.status == "DELETED"

        # Verify audit event was created
        audit_events = await session.execute(
            AuditEvent.__table__.select().where(AuditEvent.entity_id == test_entity.id)
        )
        events = audit_events.fetchall()
        assert len(events) > 0

        # Check the most recent event
        latest_event = max(events, key=lambda e: e.timestamp)
        assert latest_event.action_type == AuditEventType.DELETE
        assert latest_event.entity_type == "AuditTestEntity"
        assert latest_event.entity_id == test_entity.id
        assert latest_event.actor_id == system_user.id

    @pytest.mark.asyncio
    async def test_entity_param_not_found_error(
        self,
        test_service: TestEntityService,
        session: AsyncSession,
        system_user: Player,
    ):
        """Test error when entity_param specifies non-existent parameter"""

        # Create a service method with incorrect entity_param
        class BadService:
            @AuditService.audited_transaction(
                action_type=AuditEventType.UPDATE,
                entity_type="AuditTestEntity",
                entity_param="nonexistent_param",  # This parameter doesn't exist
            )
            async def bad_method(
                self, entity: AuditTestEntity, actor: Player, session: AsyncSession
            ) -> AuditTestEntity:
                return entity

        service = BadService()
        test_entity = AuditTestEntity(name="Test")

        # Should raise an error about missing parameter
        with pytest.raises(
            ValueError, match="Entity parameter 'nonexistent_param' not found"
        ):
            await service.bad_method(test_entity, system_user, session)

    @pytest.mark.asyncio
    async def test_entity_param_is_none(
        self,
        test_service: TestEntityService,
        session: AsyncSession,
        system_user: Player,
    ):
        """Test error when entity_param points to None value"""

        # Try to update with None entity
        with pytest.raises(
            ValueError, match="Entity parameter 'target_entity' not found or is None"
        ):
            await test_service.update_entity_with_param(
                uuid4(),
                None,  # target_entity is None
                999,
                system_user,
                session,
            )
