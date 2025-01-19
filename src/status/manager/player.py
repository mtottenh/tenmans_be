
# Initialize Player status transition manager
from auth.schemas import PlayerStatus
from status.transition_validator import HasRequiredReasonValidator, StatusTransitionManager, StatusTransitionRule, SuspensionDurationValidator


def initialize_player_status_manager() -> StatusTransitionManager:
    manager = StatusTransitionManager( 
        status_enum=PlayerStatus,
        entity_type="Player"
    )
    
    # Define transition rules

    # Verification flow
    # Pending Verification -> Active user (Admin Acc activation)
    manager.add_rule(StatusTransitionRule(
        from_status={PlayerStatus.PENDING_VERIFICATION},
        to_status={PlayerStatus.ACTIVE},
        validators=[HasRequiredReasonValidator()],
        required_permissions=["verify_users"]
    ))
    
    # Pending Verification -> Verification Rejected (Admin Acc Rejection)
    manager.add_rule(StatusTransitionRule(
        from_status={PlayerStatus.PENDING_VERIFICATION},
        to_status={PlayerStatus.VERIFICATION_REJECTED},
        validators=[HasRequiredReasonValidator()],
        required_permissions=["verify_users"]
    ))

    
    # Verification Rejected -> Pending Verification (Admin Reactivation from rejected)
    manager.add_rule(StatusTransitionRule(
        from_status={PlayerStatus.VERIFICATION_REJECTED},
        to_status={PlayerStatus.PENDING_VERIFICATION},
        validators=[HasRequiredReasonValidator()],
        required_permissions=["verify_users"]
    ))

    # Active -> Inactive (self-deactivation)
    manager.add_rule(StatusTransitionRule(
        from_status={PlayerStatus.ACTIVE},
        to_status={PlayerStatus.INACTIVE},
        validators=[HasRequiredReasonValidator()],
        required_permissions=["user"]  # Basic user permission
    ))
    
    # Active -> Suspended (admin action)
    manager.add_rule(StatusTransitionRule(
        from_status={PlayerStatus.ACTIVE},
        to_status={PlayerStatus.SUSPENDED},
        validators=[
            HasRequiredReasonValidator(),
            SuspensionDurationValidator()
        ],
        required_permissions=["manage_users"]
    ))
    
    # Active -> Banned (admin action)
    manager.add_rule(StatusTransitionRule(
        from_status={PlayerStatus.ACTIVE, PlayerStatus.SUSPENDED},
        to_status={PlayerStatus.BANNED},
        validators=[HasRequiredReasonValidator()],
        required_permissions=["manage_bans"]
    ))
    
    # Any -> Deleted (admin action)
    manager.add_rule(StatusTransitionRule(
        from_status=None,  # Can transition from any status
        to_status={PlayerStatus.DELETED},
        validators=[HasRequiredReasonValidator()],
        required_permissions=["manage_users"]
    ))
    
    # Suspended -> Active (admin action)
    manager.add_rule(StatusTransitionRule(
        from_status={PlayerStatus.SUSPENDED},
        to_status={PlayerStatus.ACTIVE},
        validators=[HasRequiredReasonValidator()],
        required_permissions=["manage_users"]
    ))
    
    # Inactive -> Active (user action)
    manager.add_rule(StatusTransitionRule(
        from_status={PlayerStatus.INACTIVE},
        to_status={PlayerStatus.ACTIVE},
        validators=[HasRequiredReasonValidator()],
        required_permissions=["user"]
    ))
    
    return manager