from typing import Any, Dict
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.schemas import ScopeType
from auth.models import Player
from auth.service.permission import PermissionScope, PermissionService
from competitions.models.tournaments import Tournament, TournamentState
from status.transition_validator import StatusTransitionManager, StatusTransitionRule, TransitionValidator


class TournamentTransitionPermissionValidator(TransitionValidator):
    """Validates permissions for tournament status transitions based on actor role"""
    
    async def validate(
        self,
        current_status: TournamentState,
        new_status: TournamentState,
        context: Dict[str, Any]
    ) -> bool:
        actor: Player = context.get('actor')
        session: AsyncSession = context.get('session')
        entity: Tournament = context.get('entity')  # The Tournament entity
        permission_service: PermissionService = context.get('permission_service')
        
        if not actor or not session or not entity or not permission_service:
            raise ValueError("Missing required context for permission validation")

        # Check if actor is admin - admins can do any transition
        is_admin = await permission_service.verify_permissions(
            actor,
            ["manage_tournaments"],
            None,  # Global scope
            session
        )
        if is_admin:
            return True

        # Check if actor is tournament admin
        is_tournament_admin = await permission_service.verify_permissions(
            actor,
            ["manage_tournament"],
            PermissionScope(ScopeType.TOURNAMENT, entity.id),
            session
        )
        return is_tournament_admin


def initialize_tournament_status_manager() -> StatusTransitionManager:
    """Initialize the tournament status transition manager with rules"""
    manager = StatusTransitionManager(
        status_enum=TournamentState,
        entity_type="Tournament"
    )
    
    # Define valid transitions
    # From NOT_STARTED
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.NOT_STARTED,
        to_status=TournamentState.REGISTRATION_OPEN,
        validators=[TournamentTransitionPermissionValidator()]
    ))
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.NOT_STARTED,
        to_status=TournamentState.CANCELLED,
        validators=[TournamentTransitionPermissionValidator()]
    ))
    
    # From REGISTRATION_OPEN  
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.REGISTRATION_OPEN,
        to_status=TournamentState.REGISTRATION_CLOSED,
        validators=[TournamentTransitionPermissionValidator()]
    ))
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.REGISTRATION_OPEN,
        to_status=TournamentState.CANCELLED,
        validators=[TournamentTransitionPermissionValidator()]
    ))
    
    # From REGISTRATION_CLOSED
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.REGISTRATION_CLOSED,
        to_status=TournamentState.IN_PROGRESS,
        validators=[TournamentTransitionPermissionValidator()]
    ))
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.REGISTRATION_CLOSED,
        to_status=TournamentState.CANCELLED,
        validators=[TournamentTransitionPermissionValidator()]
    ))
    
    # From READY
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.IN_PROGRESS,
        to_status=TournamentState.CANCELLED,
        validators=[TournamentTransitionPermissionValidator()]
    ))
    
    # From IN_PROGRESS
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.IN_PROGRESS,
        to_status=TournamentState.COMPLETED,
        validators=[TournamentTransitionPermissionValidator()]
    ))

    
    # Additional transition for structure generation
    manager.add_rule(StatusTransitionRule(
        from_status=TournamentState.REGISTRATION_CLOSED,
        to_status=TournamentState.NOT_STARTED,
        validators=[TournamentTransitionPermissionValidator()]
    ))
    
    return manager