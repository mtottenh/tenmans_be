"""Result status transition manager and validators"""

from typing import Any, Optional

from auth.models import Player
from auth.service.permission import PermissionService, create_permission_service
from matches.models import ConfirmationStatus
from status.transition_validator import (
    TransitionValidator,
    StatusTransitionManager,
    StatusTransitionRule,
    TransitionError,
)


class ResultTransitionValidator(TransitionValidator):
    """Validates result status transitions"""
    
    async def validate(
        self,
        old_status: ConfirmationStatus,
        new_status: ConfirmationStatus,
        context: dict[str, Any],
    ) -> bool:
        """Validate if the result transition is allowed"""
        actor = context.get("actor")
        result = context.get("entity")
        
        if not actor or not result:
            return False
            
        # Define valid transitions
        valid_transitions = {
            ConfirmationStatus.PENDING: [
                ConfirmationStatus.CONFIRMED,
                ConfirmationStatus.DISPUTED,
                ConfirmationStatus.ADMIN_OVERRIDE,
                ConfirmationStatus.VOIDED,
            ],
            ConfirmationStatus.CONFIRMED: [
                ConfirmationStatus.DISPUTED,
                ConfirmationStatus.ADMIN_OVERRIDE,
                ConfirmationStatus.VOIDED,
            ],
            ConfirmationStatus.DISPUTED: [
                ConfirmationStatus.CONFIRMED,
                ConfirmationStatus.ADMIN_OVERRIDE,
                ConfirmationStatus.VOIDED,
            ],
            ConfirmationStatus.ADMIN_OVERRIDE: [
                ConfirmationStatus.VOIDED,
            ],
            ConfirmationStatus.VOIDED: [],  # No transitions from voided
        }
        
        # Check if transition is valid
        if new_status not in valid_transitions.get(old_status, []):
            raise TransitionError(
                f"Invalid transition from {old_status} to {new_status}"
            )
            
        # Check permissions based on target status
        permission_service = context.get("permission_service")
        if not permission_service:
            permission_service = create_permission_service()
            
        if new_status in [ConfirmationStatus.ADMIN_OVERRIDE, ConfirmationStatus.VOIDED]:
            # Only admins can override or void results
            if not permission_service.has_global_permission(actor, "match_override"):
                raise TransitionError("Admin permission required")
                
        elif new_status == ConfirmationStatus.CONFIRMED:
            # Only opposing team captain can confirm
            fixture = result.fixture
            if old_status == ConfirmationStatus.PENDING:
                # Confirm from pending - must be opposing captain
                if result.submitted_by == actor.id:
                    raise TransitionError("Cannot confirm your own result submission")
                    
                # Check if actor is captain of opposing team
                is_team1_captain = str(actor.id) in [str(c.player_id) for c in fixture.team_1_obj.captains]
                is_team2_captain = str(actor.id) in [str(c.player_id) for c in fixture.team_2_obj.captains]
                
                if not (is_team1_captain or is_team2_captain):
                    raise TransitionError("Only team captains can confirm results")
                    
        elif new_status == ConfirmationStatus.DISPUTED:
            # Only opposing team can dispute
            if result.submitted_by == actor.id:
                raise TransitionError("Cannot dispute your own result submission")
                
        return True


class ResultAuthorityValidator(TransitionValidator):
    """Validates the actor has authority to transition result status"""
    
    async def validate(
        self,
        old_status: ConfirmationStatus,
        new_status: ConfirmationStatus,
        context: dict[str, Any],
    ) -> bool:
        """Check if actor has authority for this transition"""
        actor = context.get("actor")
        result = context.get("entity")
        
        if not actor or not result:
            return False
            
        # Admins can do any transition
        permission_service = context.get("permission_service")
        if permission_service.has_global_permission(actor, "match_override"):
            return True
            
        # Check specific transition authority
        if new_status == ConfirmationStatus.ADMIN_OVERRIDE:
            # Only admins (already checked above)
            return False
            
        # Team captains have authority for their team's matches
        fixture = result.fixture
        is_captain = False
        
        # Check if actor is captain of either team
        for team in [fixture.team_1_obj, fixture.team_2_obj]:
            if str(actor.id) in [str(c.player_id) for c in team.captains]:
                is_captain = True
                break
                
        return is_captain


def initialize_result_status_manager(
    permission_service: Optional[PermissionService] = None,
) -> StatusTransitionManager:
    """Initialize and configure the result status transition manager"""
    manager = StatusTransitionManager(
        status_enum=ConfirmationStatus,
        entity_type="Result",
    )
    
    # Create rules with validators
    validators = [ResultTransitionValidator(), ResultAuthorityValidator()]
    
    # Pending -> Other states
    from_pending_rule = StatusTransitionRule(
        from_status={ConfirmationStatus.PENDING},
        to_status={
            ConfirmationStatus.CONFIRMED,
            ConfirmationStatus.DISPUTED,
            ConfirmationStatus.ADMIN_OVERRIDE,
            ConfirmationStatus.VOIDED
        },
        validators=validators
    )
    manager.add_rule(from_pending_rule)
    
    # Confirmed -> Other states
    from_confirmed_rule = StatusTransitionRule(
        from_status={ConfirmationStatus.CONFIRMED},
        to_status={
            ConfirmationStatus.DISPUTED,
            ConfirmationStatus.ADMIN_OVERRIDE,
            ConfirmationStatus.VOIDED
        },
        validators=validators
    )
    manager.add_rule(from_confirmed_rule)
    
    # Disputed -> Other states
    from_disputed_rule = StatusTransitionRule(
        from_status={ConfirmationStatus.DISPUTED},
        to_status={
            ConfirmationStatus.CONFIRMED,
            ConfirmationStatus.ADMIN_OVERRIDE,
            ConfirmationStatus.VOIDED
        },
        validators=validators
    )
    manager.add_rule(from_disputed_rule)
    
    # Admin Override -> Voided only
    from_override_rule = StatusTransitionRule(
        from_status={ConfirmationStatus.ADMIN_OVERRIDE},
        to_status={ConfirmationStatus.VOIDED},
        validators=validators
    )
    manager.add_rule(from_override_rule)
    
    return manager