from typing import Any, Dict
from audit.schemas import ScopeType
from auth.models import Player
from auth.service.permission import PermissionScope, PermissionService
from status.transition_validator import StatusTransitionManager, StatusTransitionRule, TransitionValidator
from teams.base_schemas import TeamStatus
from teams.models import Team



class TeamTransitionPermissionValidator(TransitionValidator):
    """Validates permissions for roster status transitions based on actor role"""
    
    async def validate(
        self,
        current_status: TeamStatus,
        new_status: TeamStatus,
        context: Dict[str, Any]
    ) -> bool:
        actor: Player = context.get('actor')
        session: AsyncSession = context.get('session')
        entity: Team = context.get('entity')  # The Team entry
        permission_service: PermissionService = context.get('permission_service')
        
        if not actor or not session or not entity or not permission_service:
            raise ValueError("Missing required context for permission validation")

        # Check if actor is admin - admins can do any transition
        is_admin = await permission_service.verify_permissions(
            actor,
            ["manage_teams"],
            None,  # Global scope
            session
        )
        if is_admin:
            return True

        # Check if actor is team captain
        is_captain = await permission_service.verify_permissions(
            actor,
            ["manage_team"],
            PermissionScope(ScopeType.TEAM, entity.id),
            session
        )
        return is_captain
    
def initialize_team_status_manager() -> StatusTransitionManager:
    """Initialize the team status transition manager with rules"""
    manager = StatusTransitionManager(
        status_enum=TeamStatus,
        entity_type="Team"
    )
    
    # Basic validation that a reason is provided
    class TeamStatusReasonValidator(TransitionValidator):
        async def validate(self, current_status, new_status, context):
            reason = context.get('reason')
            if not reason or not reason.strip():
                raise ValueError("A reason must be provided for team status changes")
            return True

    # Validator to ensure no active matches when disbanding
    class NoActiveMatchesValidator(TransitionValidator):
        async def validate(self, current_status, new_status, context):
            if new_status == TeamStatus.DISBANDED:
                # TODO: Add check for active matches when match service is implemented
                pass
            return True

    # Define transition rules
    
    # Active -> Disbanded (admin action or team captain)
    manager.add_rule(StatusTransitionRule(
        from_status={TeamStatus.ACTIVE},
        to_status={TeamStatus.DISBANDED},
        validators=[TeamStatusReasonValidator(), NoActiveMatchesValidator(), TeamTransitionPermissionValidator()],

    ))
    
    # Active -> Suspended (admin action)
    manager.add_rule(StatusTransitionRule(
        from_status={TeamStatus.ACTIVE},
        to_status={TeamStatus.SUSPENDED},
        validators=[TeamStatusReasonValidator()],
        required_permissions=["manage_teams"]
    ))
    
    # Suspended -> Active (admin action)
    manager.add_rule(StatusTransitionRule(
        from_status={TeamStatus.SUSPENDED},
        to_status={TeamStatus.ACTIVE},
        validators=[TeamStatusReasonValidator()],
        required_permissions=["manage_teams"]
    ))
    
    # Any -> Archived (admin only)
    manager.add_rule(StatusTransitionRule(
        from_status=None,  # Can transition from any status
        to_status={TeamStatus.ARCHIVED},
        validators=[TeamStatusReasonValidator()],
        required_permissions=["admin"]
    ))

    return manager