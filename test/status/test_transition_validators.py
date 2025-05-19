from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, ClassVar

import pytest

from status.transition_validator import (
    HasRequiredReasonValidator,
    SuspensionDurationValidator,
    TransitionValidator,
)


# Test status enum
class EntityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


# Custom validators for testing
class DateRangeValidator(TransitionValidator):
    """Validates that transition happens within a specific date range"""

    def __init__(self, start_date: datetime, end_date: datetime):
        self.start_date = start_date
        self.end_date = end_date

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        now = datetime.now(timezone.utc)
        return self.start_date <= now <= self.end_date


class EntityAttributeValidator(TransitionValidator):
    """Validates based on entity attributes"""

    def __init__(self, attribute: str, expected_value: Any):
        self.attribute = attribute
        self.expected_value = expected_value

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        entity = context.get("entity")
        if not entity:
            return False

        return getattr(entity, self.attribute, None) == self.expected_value


class MultiFieldValidator(TransitionValidator):
    """Validates multiple fields exist and meet criteria"""

    def __init__(self, required_fields: dict[str, Any]):
        self.required_fields = required_fields

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        for field, expected in self.required_fields.items():
            if field not in context:
                return False
            if expected is not None and context[field] != expected:
                return False
        return True


class ConditionalValidator(TransitionValidator):
    """Validates based on complex conditions"""

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        # Example: Only allow archiving if entity is older than 30 days
        if str(new_status) == "ARCHIVED":
            entity = context.get("entity")
            if entity and hasattr(entity, "created_at"):
                age = datetime.now(timezone.utc) - entity.created_at
                return age.days > 30
        return True


class UserRoleValidator(TransitionValidator):
    """Validates user has specific role"""

    def __init__(self, required_role: str):
        self.required_role = required_role

    async def validate(
        self, current_status: StrEnum, new_status: StrEnum, context: dict[str, Any]
    ) -> bool:
        actor = context.get("actor")
        if not actor:
            return False

        # In a real scenario, would check actor's roles
        # For testing, check a mock role attribute
        roles = getattr(actor, "roles", [])
        return self.required_role in roles


class TestTransitionValidators:
    """Test various transition validators"""

    @pytest.mark.asyncio
    async def test_has_required_reason_validator(self):
        """Test the built-in HasRequiredReasonValidator"""
        validator = HasRequiredReasonValidator()

        # Test with no reason
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {}
        )
        assert result is False

        # Test with empty string reason
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {"reason": ""}
        )
        assert result is False

        # Test with whitespace-only reason
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {"reason": "   \t\n   "}
        )
        assert result is False

        # Test with valid reason
        result = await validator.validate(
            EntityStatus.ACTIVE,
            EntityStatus.SUSPENDED,
            {"reason": "Valid suspension reason"},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_suspension_duration_validator(self):
        """Test the built-in SuspensionDurationValidator"""
        validator = SuspensionDurationValidator()

        # Test transition to SUSPENDED without end_date
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {}
        )
        assert result is False

        # Test transition to SUSPENDED with end_date
        result = await validator.validate(
            EntityStatus.ACTIVE,
            EntityStatus.SUSPENDED,
            {"end_date": datetime.now(timezone.utc) + timedelta(days=7)},
        )
        assert result is True

        # Test transition not to SUSPENDED (should always pass)
        result = await validator.validate(
            EntityStatus.SUSPENDED, EntityStatus.ACTIVE, {}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_date_range_validator(self):
        """Test custom date range validator"""
        # Create validator for next week
        start = datetime.now(timezone.utc) + timedelta(days=7)
        end = datetime.now(timezone.utc) + timedelta(days=14)
        validator = DateRangeValidator(start, end)

        # Test current date (should fail)
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.ARCHIVED, {}
        )
        assert result is False

        # Create validator for current time
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc) + timedelta(hours=1)
        validator = DateRangeValidator(start, end)

        # Test current date (should pass)
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.ARCHIVED, {}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_entity_attribute_validator(self):
        """Test entity attribute validator"""
        validator = EntityAttributeValidator("type", "premium")

        # Mock entity
        class MockEntity:
            def __init__(self, type_value):
                self.type = type_value

        # Test with matching attribute
        entity = MockEntity("premium")
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {"entity": entity}
        )
        assert result is True

        # Test with non-matching attribute
        entity = MockEntity("basic")
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {"entity": entity}
        )
        assert result is False

        # Test without entity
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_multi_field_validator(self):
        """Test multi-field validator"""
        validator = MultiFieldValidator(
            {
                "approved_by": None,  # Must exist but any value
                "approval_date": None,  # Must exist but any value
                "priority": "high",  # Must exist and equal 'high'
            }
        )

        # Test with all fields correct
        context = {
            "approved_by": "manager",
            "approval_date": datetime.now(timezone.utc),
            "priority": "high",
        }
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.ARCHIVED, context
        )
        assert result is True

        # Test with missing field
        context = {"approved_by": "manager", "priority": "high"}
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.ARCHIVED, context
        )
        assert result is False

        # Test with wrong value
        context = {
            "approved_by": "manager",
            "approval_date": datetime.now(timezone.utc),
            "priority": "low",
        }
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.ARCHIVED, context
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_conditional_validator(self):
        """Test conditional validator"""
        validator = ConditionalValidator()

        # Mock entity
        class MockEntity:
            def __init__(self, created_at):
                self.created_at = created_at

        # Test with old entity (should pass)
        old_entity = MockEntity(datetime.now(timezone.utc) - timedelta(days=45))
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.ARCHIVED, {"entity": old_entity}
        )
        assert result is True

        # Test with new entity (should fail)
        new_entity = MockEntity(datetime.now(timezone.utc) - timedelta(days=15))
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.ARCHIVED, {"entity": new_entity}
        )
        assert result is False

        # Test non-archive transition (should pass)
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {"entity": new_entity}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_user_role_validator(self):
        """Test user role validator"""
        validator = UserRoleValidator("admin")

        # Mock actor
        class MockActor:
            def __init__(self, roles):
                self.roles = roles

        # Test with correct role
        admin_user = MockActor(["user", "admin", "moderator"])
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {"actor": admin_user}
        )
        assert result is True

        # Test without correct role
        regular_user = MockActor(["user"])
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {"actor": regular_user}
        )
        assert result is False

        # Test without actor
        result = await validator.validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, {}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_validator_composition(self):
        """Test combining multiple validators"""
        # Create a complex validation scenario
        validators = [
            HasRequiredReasonValidator(),
            EntityAttributeValidator("status", "active"),
            UserRoleValidator("manager"),
        ]

        # Mock objects
        class MockEntity:
            status = "active"

        class MockActor:
            roles: ClassVar[list[str]] = ["manager", "user"]

        context = {
            "reason": "Valid reason",
            "entity": MockEntity(),
            "actor": MockActor(),
        }

        # All validators should pass
        for validator in validators:
            result = await validator.validate(
                EntityStatus.ACTIVE, EntityStatus.SUSPENDED, context
            )
            assert result is True

        # Remove reason - first validator should fail
        del context["reason"]
        result = await validators[0].validate(
            EntityStatus.ACTIVE, EntityStatus.SUSPENDED, context
        )
        assert result is False
