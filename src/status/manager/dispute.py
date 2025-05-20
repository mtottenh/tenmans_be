"""Dispute status transition manager and validators"""

from typing import Any, Optional

from auth.models import Player
from auth.service.permission import PermissionService, create_permission_service
from matches.models import DisputeStatus
from status.transition_validator import (
    TransitionValidator,
    StatusTransitionManager,
    StatusTransitionRule,
    TransitionError,
)


class DisputeTransitionValidator(TransitionValidator):
    """Validates dispute status transitions"""
    
    async def validate(
        self,
        old_status: DisputeStatus,
        new_status: DisputeStatus,
        context: dict[str, Any],
    ) -> bool:
        """Validate if the dispute transition is allowed"""
        actor = context.get("actor")
        dispute = context.get("entity")
        
        if not actor or not dispute:
            return False
            
        # Define valid transitions
        valid_transitions = {
            DisputeStatus.PENDING: [
                DisputeStatus.UNDER_REVIEW,
                DisputeStatus.RESOLVED,
                DisputeStatus.REJECTED,
            ],
            DisputeStatus.UNDER_REVIEW: [
                DisputeStatus.RESOLVED,
                DisputeStatus.REJECTED,
                DisputeStatus.ESCALATED,
            ],
            DisputeStatus.RESOLVED: [],  # Terminal state
            DisputeStatus.REJECTED: [],  # Terminal state
            DisputeStatus.ESCALATED: [
                DisputeStatus.RESOLVED,
                DisputeStatus.REJECTED,
            ],
        }
        
        # Check if transition is valid
        if new_status not in valid_transitions.get(old_status, []):
            raise TransitionError(
                f"Invalid transition from {old_status} to {new_status}"
            )
            
        return True


class DisputeAuthorityValidator(TransitionValidator):
    """Validates the actor has authority to transition dispute status"""
    
    async def validate(
        self,
        old_status: DisputeStatus,
        new_status: DisputeStatus,
        context: dict[str, Any],
    ) -> bool:
        """Check if actor has authority for this transition"""
        actor = context.get("actor")
        dispute = context.get("entity")
        
        if not actor or not dispute:
            return False
            
        permission_service = context.get("permission_service")
        if not permission_service:
            permission_service = create_permission_service()
            
        # Only admins can transition dispute statuses
        if not permission_service.has_global_permission(actor, "dispute_management"):
            raise TransitionError("Admin permission required for dispute management")
            
        # Additional checks for specific transitions
        if new_status == DisputeStatus.ESCALATED:
            # Only certain admins can escalate
            if not permission_service.has_global_permission(actor, "dispute_escalation"):
                raise TransitionError("Escalation permission required")
                
        return True


class DisputeReasonValidator(TransitionValidator):
    """Ensures resolution/rejection includes a reason"""
    
    async def validate(
        self,
        old_status: DisputeStatus,
        new_status: DisputeStatus,
        context: dict[str, Any],
    ) -> bool:
        """Check if reason is provided for resolution/rejection"""
        if new_status in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            reason = context.get("reason")
            if not reason:
                raise TransitionError("Reason required for dispute resolution/rejection")
                
        return True


def initialize_dispute_status_manager(
    permission_service: Optional[PermissionService] = None,
) -> StatusTransitionManager:
    """Initialize and configure the dispute status transition manager"""
    manager = StatusTransitionManager(
        status_enum=DisputeStatus,
        entity_type="MatchDispute",
    )
    
    # Create rules with validators
    from_pending_rule = StatusTransitionRule(
        from_status={DisputeStatus.PENDING},
        to_status={DisputeStatus.UNDER_REVIEW, DisputeStatus.RESOLVED, DisputeStatus.REJECTED},
        validators=[DisputeTransitionValidator(), DisputeAuthorityValidator(), DisputeReasonValidator()]
    )
    manager.add_rule(from_pending_rule)
    
    from_review_rule = StatusTransitionRule(
        from_status={DisputeStatus.UNDER_REVIEW},
        to_status={DisputeStatus.RESOLVED, DisputeStatus.REJECTED, DisputeStatus.ESCALATED},
        validators=[DisputeTransitionValidator(), DisputeAuthorityValidator(), DisputeReasonValidator()]
    )
    manager.add_rule(from_review_rule)
    
    from_escalated_rule = StatusTransitionRule(
        from_status={DisputeStatus.ESCALATED},
        to_status={DisputeStatus.RESOLVED, DisputeStatus.REJECTED},
        validators=[DisputeTransitionValidator(), DisputeAuthorityValidator(), DisputeReasonValidator()]
    )
    manager.add_rule(from_escalated_rule)
    
    return manager