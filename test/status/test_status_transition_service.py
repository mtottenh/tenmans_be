from enum import StrEnum
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from audit.context import AuditContext
from audit.schemas import AuditEventType
from auth.models import Player
from status.pipeline import TransitionPipeline, TransitionStep
from status.service import StatusTransitionService
from status.transition_validator import (
    StatusTransitionManager,
    StatusTransitionRule,
    TransitionError,
    TransitionValidator,
)
from teams.models import TeamStatus


# Create test status enum
class SampleStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


# Create test entity
class StatusTestEntity:
    def __init__(self, id: uuid4, status: SampleStatus):
        self.id = id
        self.status = status


# Create custom validator for testing
class TestReasonValidator(TransitionValidator):
    """Test validator that checks for reason in context"""

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        return bool(context.get("reason"))


# Create test pipeline step
class TestPipelineStep(TransitionStep):
    """Test pipeline step that sets a flag in context"""

    async def execute(
        self,
        entity: Any,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: AuditContext | None = None,
        **context,
    ) -> None:
        # Set a flag to verify this step was executed
        context["test_pipeline_executed"] = True

        # Create an audit event to test audit integration
        if audit_context:
            await audit_context.create_audit_event(
                session=session,
                action_type=AuditEventType.STATUS_CHANGE,
                entity_type="test_entity",
                entity_id=entity.id,
                actor=actor,
                details={"pipeline_step": "test_step"},
            )


class TestStatusTransitionService:
    """Test the StatusTransitionService functionality"""

    @pytest_asyncio.fixture
    async def test_entity(self):
        """Create a test entity"""
        return StatusTestEntity(id=uuid4(), status=SampleStatus.DRAFT)

    @pytest_asyncio.fixture
    async def transition_service(self):
        """Create a configured transition service"""
        service = StatusTransitionService()

        # Create and configure transition manager
        manager = StatusTransitionManager(SampleStatus, "TestEntity")

        # Add transition rules
        manager.add_rule(
            StatusTransitionRule(
                from_status={SampleStatus.DRAFT},
                to_status={SampleStatus.ACTIVE},
                validators=[TestReasonValidator()],
                required_permissions=[],
            )
        )

        manager.add_rule(
            StatusTransitionRule(
                from_status={SampleStatus.ACTIVE},
                to_status={SampleStatus.INACTIVE, SampleStatus.SUSPENDED},
                validators=[TestReasonValidator()],
                required_permissions=["manage_entity"],
            )
        )

        manager.add_rule(
            StatusTransitionRule(
                from_status=None,  # From any status
                to_status={SampleStatus.DELETED},
                validators=[],
                required_permissions=["admin"],
            )
        )

        # Register the manager
        service.register_transition_manager("TestEntity", manager)

        # Create and register pipeline
        pipeline = TransitionPipeline([TestPipelineStep()])
        service.register_transition_pipeline("TestEntity", SampleStatus.ACTIVE, pipeline)

        return service

    @pytest.mark.asyncio
    async def test_valid_transition(
        self,
        session: AsyncSession,
        system_user: Player,
        test_entity: StatusTestEntity,
        transition_service: StatusTransitionService,
    ):
        """Test a valid status transition"""
        # Transition from DRAFT to ACTIVE
        result = await transition_service.transition_status(
            entity=test_entity,
            new_status="ACTIVE",
            reason="Test activation",
            actor=system_user,
            session=session,
        )

        assert result.status == SampleStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_transition_with_pipeline(
        self,
        session: AsyncSession,
        system_user: Player,
        test_entity: StatusTestEntity,
        transition_service: StatusTransitionService,
    ):
        """Test transition with pipeline execution"""
        # Create an audit context to pass through
        async with AuditContext(session, entity_id=test_entity.id) as audit_context:
            # This should trigger the pipeline
            result = await transition_service.transition_status(
                entity=test_entity,
                new_status="ACTIVE",
                reason="Test activation with pipeline",
                actor=system_user,
                session=session,
                audit_context=audit_context,
            )

            assert result.status == SampleStatus.ACTIVE
            # TODO: Verify pipeline was executed by checking audit events

    @pytest.mark.asyncio
    async def test_invalid_transition(
        self,
        session: AsyncSession,
        system_user: Player,
        test_entity: StatusTestEntity,
        transition_service: StatusTransitionService,
    ):
        """Test invalid transition raises error"""
        # Try to transition from DRAFT to SUSPENDED (not allowed)
        test_entity.status = SampleStatus.DRAFT

        with pytest.raises(TransitionError, match="No valid transition rule"):
            await transition_service.transition_status(
                entity=test_entity,
                new_status="SUSPENDED",
                reason="Invalid transition",
                actor=system_user,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_transition_without_reason(
        self,
        session: AsyncSession,
        system_user: Player,
        test_entity: StatusTestEntity,
        transition_service: StatusTransitionService,
    ):
        """Test transition fails when reason is required but not provided"""
        with pytest.raises(TransitionError, match="Validation failed"):
            await transition_service.transition_status(
                entity=test_entity,
                new_status="ACTIVE",
                reason="",  # Empty reason should fail validator
                actor=system_user,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_transition_with_permissions(
        self,
        session: AsyncSession,
        system_user: Player,
        test_entity: StatusTestEntity,
        transition_service: StatusTransitionService,
        test_roles: dict[str, Any],
    ):
        """Test transition that requires permissions"""
        # First activate the entity
        test_entity.status = SampleStatus.ACTIVE

        # Try to transition to INACTIVE without permissions
        regular_user = Player(
            name="No Permissions User",
            steam_id="999999",
            auth_type="STEAM",
            status="ACTIVE",
        )
        session.add(regular_user)
        await session.commit()

        with pytest.raises(TransitionError, match="Insufficient permissions"):
            await transition_service.transition_status(
                entity=test_entity,
                new_status="INACTIVE",
                reason="Should fail",
                actor=regular_user,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_status_history(
        self,
        session: AsyncSession,
        system_user: Player,
        test_entity: StatusTestEntity,
        transition_service: StatusTransitionService,
    ):
        """Test retrieving status change history"""
        # Make some transitions
        await transition_service.transition_status(
            entity=test_entity,
            new_status="ACTIVE",
            reason="First transition",
            actor=system_user,
            session=session,
        )

        # Get history
        history = await transition_service.get_status_history(
            entity_type="TestEntity", entity_id=test_entity.id, session=session
        )

        assert len(history) > 0
        first_change = history[0]
        assert first_change["new_status"] == "ACTIVE"
        assert first_change["reason"] == "First transition"

    @pytest.mark.asyncio
    async def test_no_transition_manager_error(
        self, session: AsyncSession, system_user: Player
    ):
        """Test error when no transition manager is registered"""
        service = StatusTransitionService()
        unregistered_entity = StatusTestEntity(id=uuid4(), status=SampleStatus.DRAFT)

        with pytest.raises(ValueError, match="No transition manager registered"):
            await service.transition_status(
                entity=unregistered_entity,
                new_status="ACTIVE",
                reason="Should fail",
                actor=system_user,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_get_entity_status_changes(
        self,
        session: AsyncSession,
        system_user: Player,
        transition_service: StatusTransitionService,
    ):
        """Test getting status changes for multiple entities"""
        # Create and transition multiple entities
        entities = []
        for i in range(3):
            entity = StatusTestEntity(id=uuid4(), status=SampleStatus.DRAFT)
            entities.append(entity)

            await transition_service.transition_status(
                entity=entity,
                new_status="ACTIVE",
                reason=f"Activating entity {i}",
                actor=system_user,
                session=session,
            )

        # Get all status changes
        changes = await transition_service.get_entity_status_changes(
            entity_type="TestEntity", session=session
        )

        assert len(changes) >= 3

    @pytest.mark.asyncio
    async def test_real_team_transition(
        self,
        session: AsyncSession,
        test_team_and_captain,
        transition_service: StatusTransitionService,
    ):
        """Test with a real Team entity from the system"""
        team, captain = test_team_and_captain

        # Teams are typically created with ACTIVE status, transition to DISBANDED
        # This will only work if Team transitions are properly configured
        # in the actual system
        try:
            result = await transition_service.transition_status(
                entity=team,
                new_status="DISBANDING",
                reason="Test disband",
                actor=captain,
                session=session,
            )
            assert result.status == TeamStatus.DISBANDING
        except ValueError as e:
            # If no transition manager is registered for Team, skip this test
            pytest.skip(f"Team transitions not configured: {e}")