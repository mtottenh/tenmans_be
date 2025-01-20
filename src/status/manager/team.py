from status.transition_validator import StatusTransitionManager, StatusTransitionRule, TransitionValidator
from teams.base_schemas import TeamStatus

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
        validators=[TeamStatusReasonValidator(), NoActiveMatchesValidator()],
        required_permissions=["manage_teams"]
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