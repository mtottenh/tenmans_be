# status/manager/availability.py
from typing import Dict, Any
from status.transition_validator import (
    StatusTransitionManager,
    StatusTransitionRule,
    TransitionValidator,
    TransitionError
)
from competitions.models.scheduling import AvailabilityStatus

class UserOnlyValidator(TransitionValidator):
    """Validates that only the user themselves can modify availability"""
    async def validate(
        self,
        current_status: AvailabilityStatus,
        new_status: AvailabilityStatus,
        context: Dict[str, Any]
    ) -> bool:
        actor = context.get('actor')
        availability = context.get('entity')
        
        if actor.id != availability.player_id:
            raise TransitionError("Only users can modify their own availability")
        return True

def initialize_availability_status_manager() -> StatusTransitionManager:
    """Initialize the availability status transition manager with rules"""
    manager = StatusTransitionManager(
        status_enum=AvailabilityStatus,
        entity_type="PlayerAvailability"
    )
    
    # Users can cancel or expire their own availability
    manager.add_rule(StatusTransitionRule(
        from_status={AvailabilityStatus.ACTIVE},
        to_status={AvailabilityStatus.CANCELLED},
        validators=[UserOnlyValidator()],
        required_permissions=["user"]
    ))
    
    # System can expire availability automatically
    manager.add_rule(StatusTransitionRule(
        from_status={AvailabilityStatus.ACTIVE},
        to_status={AvailabilityStatus.EXPIRED},
        validators=[],
        required_permissions=["system"]  # Only system processes can expire
    ))
    
    return manager