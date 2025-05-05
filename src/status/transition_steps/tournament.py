from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.tournaments import Tournament, TournamentState, TournamentRegistration, RegistrationStatus
from competitions.models.rounds import Round
from status.pipeline import TransitionStep

LOG = logging.getLogger('uvicorn.error')

class TournamentFixtureCancelStep(TransitionStep):
    """Pipeline step to cancel all scheduled/in-progress fixtures when a tournament is cancelled"""
    
    async def execute(
        self,
        entity: Tournament,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != TournamentState.CANCELLED.value:
            return  # Only act on cancellation transitions
        
        # Get all fixtures that aren't already completed
        stmt = select(Fixture).where(
            Fixture.tournament_id == entity.id,
            Fixture.status.in_([
                FixtureStatus.SCHEDULED, 
                FixtureStatus.IN_PROGRESS
            ])
        )
        result = await session.execute(stmt)
        fixtures = result.scalars().all()
        
        # Cancel each fixture
        for fixture in fixtures:
            LOG.info(f"Cancelling fixture {fixture.id} due to tournament cancellation")
            fixture.status = FixtureStatus.CANCELLED
            fixture.admin_notes = f"Tournament cancelled: {context.get('reason')}"
            fixture.updated_at = datetime.now()
            
            session.add(fixture)


class TournamentRegistrationCancelStep(TransitionStep):
    """Pipeline step to update tournament registrations when a tournament is cancelled"""
    
    async def execute(
        self,
        entity: Tournament,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != TournamentState.CANCELLED.value:
            return  # Only act on cancellation transitions
        
        # Get all active registrations
        stmt = select(TournamentRegistration).where(
            TournamentRegistration.tournament_id == entity.id,
            TournamentRegistration.status.in_([
                RegistrationStatus.PENDING, 
                RegistrationStatus.APPROVED
            ])
        )
        result = await session.execute(stmt)
        registrations = result.scalars().all()
        
        # Update registrations to withdrawn
        for registration in registrations:
            LOG.info(f"Withdrawing team {registration.team_id} from tournament due to cancellation")
            registration.status = RegistrationStatus.WITHDRAWN
            registration.withdrawn_by = actor.id
            registration.withdrawn_at = datetime.now()
            registration.withdrawal_reason = f"Tournament cancelled: {context.get('reason')}"
            
            session.add(registration)


class TournamentRoundCompleteStep(TransitionStep):
    """Pipeline step to complete all rounds when a tournament is completed"""
    
    async def execute(
        self,
        entity: Tournament,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != TournamentState.COMPLETED.value:
            return  # Only act on completion transitions
        
        # Get all rounds
        stmt = select(Round).where(
            Round.tournament_id == entity.id,
            Round.status != "completed"
        )
        result = await session.execute(stmt)
        rounds = result.scalars().all()
        
        # Mark all rounds as completed
        for tournament_round in rounds:
            LOG.info(f"Completing round {tournament_round.round_number} due to tournament completion")
            tournament_round.status = "completed"
            tournament_round.updated_at = datetime.now()
            
            session.add(tournament_round)