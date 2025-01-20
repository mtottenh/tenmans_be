from auth.models import Player
from auth.service.permission import PermissionScope, PermissionService
from status.manager.captain import TeamPermissionValidator
from status.transition_validator import StatusTransitionManager, StatusTransitionRule, TransitionValidator
from typing import Dict, Any
from teams.base_schemas import RosterStatus

from sqlmodel.ext.asyncio.session import AsyncSession
from status.transition_validator import TransitionValidator
from teams.base_schemas import RosterStatus
from typing import Dict, Any
from sqlmodel import select
from auth.schemas import ScopeType
from teams.models import Roster, TeamCaptain

class RosterTransitionPermissionValidator(TransitionValidator):
    """Validates permissions for roster status transitions based on actor role"""
    
    async def validate(
        self,
        current_status: RosterStatus,
        new_status: RosterStatus,
        context: Dict[str, Any]
    ) -> bool:
        actor: Player = context.get('actor')
        session: AsyncSession = context.get('session')
        entity: Roster = context.get('entity')  # The roster entry
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
            PermissionScope(ScopeType.TEAM, entity.team_id),
            session
        )
        
        # Define allowed transitions based on role
        if actor.id == entity.player_id:
            # Player can remove themselves from roster
            return await self._validate_player_transition(
                actor.id,
                current_status,
                new_status,
                entity
            )
        elif is_captain:
            # Team captain permissions
            return await self._validate_captain_transition(
                current_status,
                new_status
            )
        
        return False

    async def _validate_player_transition(
        self,
        player_id: str,
        current_status: RosterStatus,
        new_status: RosterStatus,
        roster: Roster
    ) -> bool:
        """Validate transitions allowed for players"""
        # Players can only remove themselves from roster
        if current_status == RosterStatus.ACTIVE and new_status == RosterStatus.REMOVED:
            return roster.player_id == player_id
        return False

    async def _validate_captain_transition(
        self,
        current_status: RosterStatus,
        new_status: RosterStatus
    ) -> bool:
        """Validate transitions allowed for team captains"""
        # Captains can manage normal roster operations
        allowed_transitions = {
            RosterStatus.PENDING: {RosterStatus.ACTIVE, RosterStatus.REMOVED},
            RosterStatus.ACTIVE: {RosterStatus.REMOVED, RosterStatus.SUSPENDED},
            RosterStatus.SUSPENDED: {RosterStatus.ACTIVE, RosterStatus.REMOVED},
        }
        
        return (current_status in allowed_transitions and 
                new_status in allowed_transitions[current_status])



class RosterReasonValidator(TransitionValidator):
    """Validates that a reason is provided for status changes"""
    async def validate(
        self,
        current_status: RosterStatus,
        new_status: RosterStatus,
        context: Dict[str, Any]
    ) -> bool:
        reason = context.get('reason')
        if not reason or not reason.strip():
            raise ValueError("A reason must be provided for roster status changes")
        return True




def initialize_roster_status_manager() -> StatusTransitionManager:
    """Initialize the roster status transition manager with rules"""
    manager = StatusTransitionManager(
        status_enum=RosterStatus,
        entity_type="Roster"
    )
    
    # Common validators
    reason_validator = RosterReasonValidator()
    permission_validator = RosterTransitionPermissionValidator()
    # Define transition rules
    
   # PENDING -> ACTIVE (When captain accepts)
    manager.add_rule(StatusTransitionRule(
        from_status={RosterStatus.PENDING},
        to_status={RosterStatus.ACTIVE},
        validators=[reason_validator, permission_validator],
    ))
    
    # ACTIVE -> REMOVED (When player is removed from roster Player should be allowed to leave)
    manager.add_rule(StatusTransitionRule(
        from_status={RosterStatus.ACTIVE},
        to_status={RosterStatus.REMOVED},
        validators=[reason_validator, permission_validator],
    ))
    
    # ACTIVE -> SUSPENDED (Admin action)
    manager.add_rule(StatusTransitionRule(
        from_status={RosterStatus.ACTIVE},
        to_status={RosterStatus.SUSPENDED},
        validators=[reason_validator, permission_validator],
    ))
    
    # SUSPENDED -> ACTIVE (Admin action)
    manager.add_rule(StatusTransitionRule(
        from_status={RosterStatus.SUSPENDED},
        to_status={RosterStatus.ACTIVE},
        validators=[reason_validator, permission_validator],
    ))

    # Any -> PAST (Season ended)
    manager.add_rule(StatusTransitionRule(
        from_status=None,  # Can transition from any status
        to_status={RosterStatus.PAST},
        validators=[reason_validator, permission_validator],
    ))
    return manager