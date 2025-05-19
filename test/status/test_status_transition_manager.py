from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import Player
from auth.service.permission import PermissionService
from status.transition_validator import (
    HasRequiredReasonValidator,
    StatusTransitionManager,
    StatusTransitionRule,
    SuspensionDurationValidator,
    TransitionError,
    TransitionValidator,
)


# Test status enum
class TaskStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ON_HOLD = "ON_HOLD"
    SUSPENDED = "SUSPENDED"


# Custom validators for testing
class MinimumReasonLengthValidator(TransitionValidator):
    """Validates that reason has minimum length"""

    def __init__(self, min_length: int = 10):
        self.min_length = min_length

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        reason = context.get("reason", "")
        return len(reason) >= self.min_length


class WorkInProgressValidator(TransitionValidator):
    """Validates conditions for starting work"""

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        # Check that assignee is provided when moving to IN_PROGRESS
        if str(new_status) == "IN_PROGRESS":
            return bool(context.get("assignee"))
        return True


class CompletionValidator(TransitionValidator):
    """Validates completion requirements"""

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        # Check that review notes exist when completing from REVIEW
        if str(current_status) == "REVIEW" and str(new_status) == "COMPLETED":
            return bool(context.get("review_notes"))
        return True


class TestStatusTransitionManager:
    """Test the StatusTransitionManager functionality"""

    @pytest_asyncio.fixture
    async def transition_manager(self):
        """Create a configured transition manager"""
        manager = StatusTransitionManager(TaskStatus, "Task")

        # Define transition rules

        # Draft can go to In Progress or Cancelled
        manager.add_rule(
            StatusTransitionRule(
                from_status={TaskStatus.DRAFT},
                to_status={TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
                validators=[WorkInProgressValidator()],
                required_permissions=[],
            )
        )

        # In Progress can go to Review, On Hold, or Cancelled
        manager.add_rule(
            StatusTransitionRule(
                from_status={TaskStatus.IN_PROGRESS},
                to_status={TaskStatus.REVIEW, TaskStatus.ON_HOLD, TaskStatus.CANCELLED},
                validators=[HasRequiredReasonValidator()],
                required_permissions=["manage_tasks"],
            )
        )

        # Review can go to Completed or back to In Progress
        manager.add_rule(
            StatusTransitionRule(
                from_status={TaskStatus.REVIEW},
                to_status={TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS},
                validators=[CompletionValidator()],
                required_permissions=["review_tasks"],
            )
        )

        # On Hold can go back to In Progress
        manager.add_rule(
            StatusTransitionRule(
                from_status={TaskStatus.ON_HOLD},
                to_status={TaskStatus.IN_PROGRESS},
                validators=[MinimumReasonLengthValidator()],
                required_permissions=[],
            )
        )

        # Any status can be suspended (except already suspended)
        manager.add_rule(
            StatusTransitionRule(
                from_status=None,  # From any status
                to_status={TaskStatus.SUSPENDED},
                validators=[SuspensionDurationValidator()],
                required_permissions=["admin"],
            )
        )

        # Suspended can go back to previous status (simplified)
        manager.add_rule(
            StatusTransitionRule(
                from_status={TaskStatus.SUSPENDED},
                to_status={TaskStatus.IN_PROGRESS, TaskStatus.DRAFT},
                validators=[],
                required_permissions=["admin"],
            )
        )

        return manager

    @pytest.mark.asyncio
    async def test_valid_transition(self, transition_manager: StatusTransitionManager):
        """Test a valid transition"""
        context = {
            "reason": "Starting work",
            "assignee": "user123",
            "actor": None,  # No permission check needed
            "session": None,
        }

        # Should not raise any exception
        await transition_manager.validate_transition(
            TaskStatus.DRAFT, TaskStatus.IN_PROGRESS, context
        )

    @pytest.mark.asyncio
    async def test_invalid_transition_no_rule(
        self, transition_manager: StatusTransitionManager
    ):
        """Test transition with no matching rule"""
        context = {"reason": "Invalid transition"}

        with pytest.raises(TransitionError, match="No valid transition rule found"):
            await transition_manager.validate_transition(
                TaskStatus.COMPLETED,
                TaskStatus.DRAFT,  # No rule allows this
                context,
            )

    @pytest.mark.asyncio
    async def test_validator_failure(self, transition_manager: StatusTransitionManager):
        """Test transition that fails validator"""
        context = {
            "reason": "Starting",
            # Missing assignee - should fail WorkInProgressValidator
        }

        with pytest.raises(
            TransitionError, match="Validation failed: WorkInProgressValidator"
        ):
            await transition_manager.validate_transition(
                TaskStatus.DRAFT, TaskStatus.IN_PROGRESS, context
            )

    @pytest.mark.asyncio
    async def test_permission_check(
        self,
        session: AsyncSession,
        system_user: Player,
        transition_manager: StatusTransitionManager,
    ):
        """Test transition with permission requirements"""
        # Create a user without permissions
        regular_user = Player(
            name="Regular User", steam_id="123456", auth_type="STEAM", status="ACTIVE"
        )
        session.add(regular_user)
        await session.commit()

        # Create permission service
        permission_service = PermissionService()

        context = {
            "reason": "Moving to review",
            "actor": regular_user,
            "session": session,
            "permission_service": permission_service,
        }

        # Should fail due to missing permissions
        with pytest.raises(TransitionError, match="Insufficient permissions"):
            await transition_manager.validate_transition(
                TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, context
            )

    @pytest.mark.asyncio
    async def test_suspension_validator(
        self,
        transition_manager: StatusTransitionManager,
        session: AsyncSession,
        system_user: Player,
    ):
        """Test suspension duration validator"""
        permission_service = PermissionService()

        # Test without end_date
        context = {
            "reason": "Suspending task",
            "actor": system_user,
            "session": session,
            "permission_service": permission_service,
        }

        with pytest.raises(
            TransitionError, match="Validation failed: SuspensionDurationValidator"
        ):
            await transition_manager.validate_transition(
                TaskStatus.IN_PROGRESS, TaskStatus.SUSPENDED, context
            )

        # Test with end_date
        context["end_date"] = datetime.now(timezone.utc)
        # This should now validate (permissions might still fail)
        try:
            await transition_manager.validate_transition(
                TaskStatus.IN_PROGRESS, TaskStatus.SUSPENDED, context
            )
        except TransitionError as e:
            # If it fails, it should be due to permissions, not validator
            assert "Insufficient permissions" in str(e)

    @pytest.mark.asyncio
    async def test_completion_validator(
        self, transition_manager: StatusTransitionManager
    ):
        """Test completion validator with review notes"""
        # Test without review notes
        context = {"reason": "Completing task"}

        with pytest.raises(
            TransitionError, match="Validation failed: CompletionValidator"
        ):
            await transition_manager.validate_transition(
                TaskStatus.REVIEW, TaskStatus.COMPLETED, context
            )

        # Test with review notes
        context["review_notes"] = "Task reviewed and approved"
        await transition_manager.validate_transition(
            TaskStatus.REVIEW, TaskStatus.COMPLETED, context
        )

    @pytest.mark.asyncio
    async def test_minimum_reason_length_validator(
        self, transition_manager: StatusTransitionManager
    ):
        """Test minimum reason length validator"""
        # Test with short reason
        context = {
            "reason": "Resume"  # Too short
        }

        with pytest.raises(
            TransitionError, match="Validation failed: MinimumReasonLengthValidator"
        ):
            await transition_manager.validate_transition(
                TaskStatus.ON_HOLD, TaskStatus.IN_PROGRESS, context
            )

        # Test with long enough reason
        context["reason"] = "Resuming work after dependencies resolved"
        await transition_manager.validate_transition(
            TaskStatus.ON_HOLD, TaskStatus.IN_PROGRESS, context
        )

    @pytest.mark.asyncio
    async def test_any_status_rule(
        self,
        transition_manager: StatusTransitionManager,
        session: AsyncSession,
        system_user: Player,
    ):
        """Test rule that applies from any status"""
        permission_service = PermissionService()
        context = {
            "reason": "Suspending all tasks",
            "end_date": datetime.now(timezone.utc),
            "actor": system_user,
            "session": session,
            "permission_service": permission_service,
        }

        # Test from multiple starting states
        for status in [TaskStatus.DRAFT, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]:
            try:
                await transition_manager.validate_transition(
                    status, TaskStatus.SUSPENDED, context
                )
            except TransitionError as e:  # noqa: PERF203
                # Only permission errors expected
                assert "Insufficient permissions" in str(e)

    @pytest.mark.asyncio
    async def test_has_required_reason_validator(self):
        """Test the built-in HasRequiredReasonValidator"""
        validator = HasRequiredReasonValidator()

        # Test with no reason
        assert not await validator.validate(
            TaskStatus.DRAFT, TaskStatus.IN_PROGRESS, {}
        )

        # Test with empty reason
        assert not await validator.validate(
            TaskStatus.DRAFT, TaskStatus.IN_PROGRESS, {"reason": "   "}
        )

        # Test with valid reason
        assert await validator.validate(
            TaskStatus.DRAFT, TaskStatus.IN_PROGRESS, {"reason": "Valid reason"}
        )
