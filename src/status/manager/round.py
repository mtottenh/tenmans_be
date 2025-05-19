# status/manager/round.py
from typing import Dict, Any
from auth.models import Player
from auth.service.permission import PermissionScope, PermissionService
from status.transition_validator import (
    StatusTransitionManager,
    StatusTransitionRule,
    TransitionValidator,
    TransitionError
)
from auth.schemas import ScopeType
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.rounds import Round
from enum import StrEnum
import logging
class RoundStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
class AllFixturesCompleteValidator(TransitionValidator):
    """Validates that all fixtures in the round are completed"""
    async def validate(
        self,
        current_status: RoundStatus,
        new_status: RoundStatus,
        context: Dict[str, Any]
    ) -> bool:
        if new_status != RoundStatus.COMPLETED:
            return True
        
        session = context.get('session')
        round_entity = context.get('entity')
        
        # Get all fixtures for the round
        stmt = select(Fixture).where(Fixture.round_id == round_entity.id)
        result = await session.execute(stmt)
        fixtures = result.scalars().all()
        
        # Check all fixtures are completed or forfeited
        pending_fixtures = [f for f in fixtures 
                          if f.status not in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]]
        if pending_fixtures:
            raise TransitionError(f"{len(pending_fixtures)} fixtures still pending completion")
        
        # Check all fixtures have winners
        for fixture in fixtures:
            winner_id = await fixture.get_winner_id(session)
            if not winner_id:
                raise TransitionError(f"Fixture {fixture.id} has no winner determined")
        
        return True

class TournamentAdminValidator(TransitionValidator):
    """Validates that the actor has tournament management permissions"""
    async def validate(
        self,
        current_status: RoundStatus,
        new_status: RoundStatus,
        context: Dict[str, Any]
    ) -> bool:
        permission_service: PermissionService = context["permission_service"]
        actor = context["actor"]
        session = context["session"]
        round_entity = context["entity"]
        logger.info(f"PermissionService: {permission_service}, actor: {actor}")
        perms = await permission_service.get_player_permissions(actor, session)
        logger.info(f"Permissions: {perms}")
        # Check tournament management permissions
        has_permission = await permission_service.verify_permissions(
            actor,
            ["manage_tournaments"],
            PermissionScope(ScopeType.TOURNAMENT, round_entity.tournament_id),
            session
        )
        
        if not has_permission:
            raise TransitionError("Only tournament managers can change round status")
        
        return True

def initialize_round_status_manager() -> StatusTransitionManager:
    """Initialize the round status transition manager with rules"""
    manager = StatusTransitionManager(
        status_enum=RoundStatus,
        entity_type="Round"
    )
    
    # Pending -> Active (start round)
    manager.add_rule(StatusTransitionRule(
        from_status={RoundStatus.PENDING},
        to_status={RoundStatus.ACTIVE},
        validators=[TournamentAdminValidator()]
    ))
    
    # Active -> Completed (complete round)
    manager.add_rule(StatusTransitionRule(
        from_status={RoundStatus.ACTIVE},
        to_status={RoundStatus.COMPLETED},
        validators=[TournamentAdminValidator(), AllFixturesCompleteValidator()]
    ))
    
    # Any -> Cancelled (cancel round)
    manager.add_rule(StatusTransitionRule(
        from_status=None,  # Can transition from any status
        to_status={RoundStatus.CANCELLED},
        validators=[TournamentAdminValidator()]
    ))
    
    return manager