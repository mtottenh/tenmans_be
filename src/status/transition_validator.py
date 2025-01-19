from typing import Dict, Generic, List, Optional, Set, Type, TypeVar, Any
from enum import StrEnum
from datetime import datetime

from sqlmodel import SQLModel

from auth.service.permission import PermissionService

T = TypeVar('T', bound=SQLModel)

class TransitionError(Exception):
    """Base exception for status transition errors"""
    pass

class TransitionValidator:
    """Base class for status transition validators"""
    
    async def validate(
        self,
        current_status: StrEnum,
        new_status: StrEnum,
        context: Dict[str, Any]
    ) -> bool:
        """Validate a status transition"""
        raise NotImplementedError

class StatusTransitionRule:
    """Defines a rule for status transitions"""
    def __init__(
        self,
        from_status: Optional[Set[StrEnum]],
        to_status: Set[StrEnum],
        validators: Optional[List[TransitionValidator]] = None,
        required_permissions: Optional[List[str]] = None
    ):
        self.from_status = from_status
        self.to_status = to_status
        self.validators = validators or []
        self.required_permissions = required_permissions or []

class StatusTransitionManager(Generic[T]):
    """Generic manager for status transitions"""
    
    def __init__(
        self,
        status_enum: Type[StrEnum],
        entity_type: str
    ):
        self.status_enum = status_enum
        self.entity_type = entity_type
        self.rules: List[StatusTransitionRule] = []
        
    def add_rule(self, rule: StatusTransitionRule):
        """Add a transition rule"""
        self.rules.append(rule)
        
    async def validate_transition(
        self,
        current_status: StrEnum,
        new_status: StrEnum,
        context: Dict[str, Any]
    ) -> None:
        """
        Validate a status transition
        
        Args:
            current_status: Current status value
            new_status: Proposed new status value
            context: Dictionary containing contextual information like:
                    - actor: The user making the change
                    - reason: Reason for the change
                    - entity: The entity being changed
                    - session: Database session
        """
        valid_rule = None
        
        for rule in self.rules:
            # Check if rule applies to this transition
            if (rule.from_status is None or current_status in rule.from_status) and \
               new_status in rule.to_status:
                valid_rule = rule
                break
                
        if not valid_rule:
            raise TransitionError(
                f"No valid transition rule found from {current_status} to {new_status}"
            )
        
        # Check permissions
        actor = context.get('actor')
        session = context.get('session')
        if actor and valid_rule.required_permissions:
            permission_service: PermissionService = context["permission_service"]
            has_permission = await permission_service.verify_permissions(
                actor,
                valid_rule.required_permissions,
                None,
                session
            )
            if not has_permission:
                raise TransitionError("Insufficient permissions for this transition")
        
        # Run validators
        for validator in valid_rule.validators:
            if not await validator.validate(current_status, new_status, context):
                raise TransitionError(f"Validation failed: {validator.__class__.__name__}")

# Example validators
class HasRequiredReasonValidator(TransitionValidator):
    """Validates that a reason is provided for status change"""
    async def validate(
        self,
        current_status: StrEnum,
        new_status: StrEnum,
        context: Dict[str, Any]
    ) -> bool:
        reason = context.get('reason')
        return bool(reason and reason.strip())

class SuspensionDurationValidator(TransitionValidator):
    """Validates suspension duration is provided"""
    async def validate(
        self,
        current_status: StrEnum,
        new_status: StrEnum,
        context: Dict[str, Any]
    ) -> bool:
        if str(new_status) == 'SUSPENDED':
            return bool(context.get('end_date'))
        return True