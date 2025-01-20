from typing import Dict, Any
from auth.models import Player
from auth.schemas import ScopeType
from status.transition_validator import (
    StatusTransitionManager,
    StatusTransitionRule,
    TransitionValidator,
    TransitionError
)
from teams.join_request.schemas import JoinRequestStatus
from auth.service.permission import PermissionScope, PermissionService
from teams.models import Team, TeamCaptain, Roster
from teams.join_request.models import TeamJoinRequest

from teams.base_schemas import RosterStatus
from sqlmodel import select

class HasValidReasonValidator(TransitionValidator):
    """Validates that a reason is provided for status changes"""
    async def validate(
        self,
        current_status: JoinRequestStatus,
        new_status: JoinRequestStatus,
        context: Dict[str, Any]
    ) -> bool:
        reason = context.get('reason')
        if not reason or not reason.strip():
            raise TransitionError("A reason must be provided for join request status changes")
        return True

class TeamCaptainValidator(TransitionValidator):
    """Validates that actor is team captain for accept/reject actions"""
    async def validate(
        self,
        current_status: JoinRequestStatus,
        new_status: JoinRequestStatus,
        context: Dict[str, Any]
    ) -> bool:
        if new_status not in [JoinRequestStatus.APPROVED, JoinRequestStatus.REJECTED]:
            return True  # Only validate for approve/reject actions
            
        actor = context.get('actor')
        session = context.get('session')
        team = context.get('entity').team
        permission_service: PermissionService = context.get('permission_service')        

        is_captain = await permission_service.verify_permissions(
            actor,
            ["manage_team"],
            PermissionScope(ScopeType.TEAM, team.id),
            session
        )
        
        if not is_captain:
            raise TransitionError("Only team captains can approve or reject join requests")
        return True

class RequesterOnlyValidator(TransitionValidator):
    """Validates that only the requesting player can cancel their request"""
    async def validate(
        self,
        current_status: JoinRequestStatus,
        new_status: JoinRequestStatus,
        context: Dict[str, Any]
    ) -> bool:
        if new_status != JoinRequestStatus.CANCELLED:
            return True  # Only validate for cancel actions
            
        actor: Player = context.get('actor')
        join_request: TeamJoinRequest = context.get('entity')
        
        if actor.id != join_request.player_id:
            raise TransitionError("Only the requesting player can cancel their join request")
        return True

# TODO - Use RosterService
class NoExistingTeamValidator(TransitionValidator):
    """Validates that player is not already on a team"""
    async def validate(
        self,
        current_status: JoinRequestStatus,
        new_status: JoinRequestStatus,
        context: Dict[str, Any]
    ) -> bool:
        if current_status is not None:  # Only validate for new requests
            return True
            
        session = context.get('session')
        join_request: TeamJoinRequest = context.get('entity')
        
        # Check for active roster entries
        stmt = select(Team).join(
            Roster,
            (Roster.team_id == Team.id) & 
            (Roster.player_id == join_request.player_id) &
            (Roster.season_id == join_request.season_id) &
            (Roster.status == RosterStatus.ACTIVE)
        )
        result = (await session.execute(stmt)).scalars()
        if result.first():
            raise TransitionError("Player is already on a team this season")
        return True

def initialize_join_request_manager() -> StatusTransitionManager:
    """Initialize the join request status transition manager with rules"""
    manager = StatusTransitionManager(
        status_enum=JoinRequestStatus,
        entity_type="TeamJoinRequest"
    )
    
    # Common validators
    common_validators = [HasValidReasonValidator()]
    
    # Rule for new requests
    manager.add_rule(StatusTransitionRule(
        from_status=None,
        to_status={JoinRequestStatus.PENDING},
        validators=[*common_validators, NoExistingTeamValidator()]
    ))
    
    # Rules for pending requests
    manager.add_rule(StatusTransitionRule(
        from_status={JoinRequestStatus.PENDING},
        to_status={JoinRequestStatus.APPROVED, JoinRequestStatus.REJECTED},
        validators=[*common_validators, TeamCaptainValidator()]
    ))
    
    manager.add_rule(StatusTransitionRule(
        from_status={JoinRequestStatus.PENDING},
        to_status={JoinRequestStatus.CANCELLED},
        validators=[*common_validators, RequesterOnlyValidator()]
    ))
    
    # Rule for request expiry (admin/system action)
    manager.add_rule(StatusTransitionRule(
        from_status={JoinRequestStatus.PENDING},
        to_status={JoinRequestStatus.EXPIRED},
        validators=[HasValidReasonValidator()],
        required_permissions=["manage_teams"]
    ))
    
    return manager