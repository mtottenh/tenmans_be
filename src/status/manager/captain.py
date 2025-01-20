# status/manager/team_captain.py
from typing import Dict, Any
from audit.models import ScopeType
from auth.service.permission import PermissionScope, PermissionService
from status.transition_validator import (
    StatusTransitionManager,
    StatusTransitionRule,
    TransitionValidator,
    TransitionError
)
from teams.base_schemas import TeamCaptainStatus

class HasValidReasonValidator(TransitionValidator):
    """Validates that a reason is provided for status changes"""
    async def validate(
        self,
        current_status: TeamCaptainStatus,
        new_status: TeamCaptainStatus,
        context: Dict[str, Any]
    ) -> bool:
        reason = context.get('reason')
        if not reason or not reason.strip():
            raise TransitionError("A reason must be provided for captain status changes")
        return True

class TeamPermissionValidator(TransitionValidator):
    """Validates team-specific permissions"""
    async def validate(
        self,
        current_status: TeamCaptainStatus,
        new_status: TeamCaptainStatus,
        context: Dict[str, Any]
    ) -> bool:
        permission_service: PermissionService = context["permission_service"]
        actor = context["actor"]
        session = context["session"]
        team = context["entity"].team

        # Allow if actor has global admin permissions for team management
        has_admin = await permission_service.verify_permissions(
            actor,
            ["manage_teams"],
            None,
            session
        )
        if has_admin:
            return True

        # Check if actor is team captain
        is_captain = await permission_service.verify_permissions(
            actor,
            ["manage_team"],
            PermissionScope(ScopeType.TEAM, team.id),
            session
        )
        if not is_captain:
            raise TransitionError("Only team captains can modify captain status")

        return True

def initialize_captain_status_manager() -> StatusTransitionManager:
    """Initialize the captain status transition manager with rules"""
    manager = StatusTransitionManager(
        status_enum=TeamCaptainStatus,
        entity_type="TeamCaptain"
    )

    # Common validators
    common_validators = [
        HasValidReasonValidator(),
        TeamPermissionValidator()
    ]

    # Define rules for status transitions
    
    # Active -> Removed (captain steps down or is removed)
    manager.add_rule(StatusTransitionRule(
        from_status={TeamCaptainStatus.ACTIVE},
        to_status={TeamCaptainStatus.REMOVED},
        validators=common_validators,
        required_permissions=["manage_team"]
    ))

    # Active -> Temporary (temporary handoff of duties)
    manager.add_rule(StatusTransitionRule(
        from_status={TeamCaptainStatus.ACTIVE},
        to_status={TeamCaptainStatus.TEMPORARY},
        validators=common_validators,
        required_permissions=["manage_team"]  
    ))

    # Temporary -> Active (resume duties)
    manager.add_rule(StatusTransitionRule(
        from_status={TeamCaptainStatus.TEMPORARY},
        to_status={TeamCaptainStatus.ACTIVE},
        validators=common_validators,
        required_permissions=["manage_team"]
    ))

    # Pending -> Active (accept captaincy)
    manager.add_rule(StatusTransitionRule(
        from_status={TeamCaptainStatus.PENDING},
        to_status={TeamCaptainStatus.ACTIVE},
        validators=common_validators,
        required_permissions=["manage_team"]
    ))

    # Pending -> Disbanded (team disbanded while pending)
    manager.add_rule(StatusTransitionRule(
        from_status={TeamCaptainStatus.PENDING},
        to_status={TeamCaptainStatus.DISBANDED},
        validators=[HasValidReasonValidator()],
        required_permissions=["manage_team"]
    ))

    # Any -> Disbanded (when team is disbanded)
    manager.add_rule(StatusTransitionRule(
        from_status=None,  # Can transition from any status
        to_status={TeamCaptainStatus.DISBANDED},
        validators=[HasValidReasonValidator()],
        required_permissions=["manage_team"]
    ))

    return manager