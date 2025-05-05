# status/transition_steps/tournament_generation.py
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from competitions.models.tournaments import Tournament, TournamentState
from competitions.models.rounds import Round
from competitions.models.fixtures import Fixture
from status.pipeline import TransitionStep

LOG = logging.getLogger('uvicorn.error')

class TournamentGenerationCleanupStep(TransitionStep):
    """Pipeline step to clean up any existing structure before regeneration"""
    
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
        # Only execute for tournaments being regenerated
        if context.get('regenerate', False):
            LOG.info(f"Cleaning up existing structure for tournament {entity.id}")
            
            # Delete existing fixtures
            stmt = select(Fixture).where(Fixture.tournament_id == entity.id)
            result = await session.execute(stmt)
            fixtures = result.scalars().all()
            
            for fixture in fixtures:
                await session.delete(fixture)
            
            # Delete existing rounds
            stmt = select(Round).where(Round.tournament_id == entity.id)
            result = await session.execute(stmt)
            rounds = result.scalars().all()
            
            for round in rounds:
                await session.delete(round)
            
            LOG.info(f"Cleaned up {len(fixtures)} fixtures and {len(rounds)} rounds")

class TournamentGenerationValidationStep(TransitionStep):
    """Pipeline step to validate tournament before generation"""
    
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
        from competitions.tournament.generation.validators import TournamentValidator
        
        LOG.info(f"Validating tournament {entity.id} configuration")
        
        try:
            TournamentValidator.validate_tournament_config(entity)
            TournamentValidator.validate_tournament_dates(entity)
        except Exception as e:
            LOG.error(f"Tournament validation failed: {str(e)}")
            raise

class TournamentRegistrationCloseStep(TransitionStep):
    """Pipeline step to close tournament registration"""
    
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
        if old_status == TournamentState.REGISTRATION_OPEN.value:
            LOG.info(f"Closing registration for tournament {entity.id}")
            entity.registration_end = datetime.now()
            session.add(entity)

class TournamentStartSetupStep(TransitionStep):
    """Pipeline step to set up tournament start"""
    
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
        if new_status == TournamentState.IN_PROGRESS.value:
            LOG.info(f"Setting up tournament start for {entity.id}")
            entity.actual_start_date = datetime.now()
            
            # Activate first round
            stmt = select(Round).where(
                Round.tournament_id == entity.id,
                Round.round_number == 1
            )
            result = await session.execute(stmt)
            first_round = result.scalar_one_or_none()
            
            if first_round:
                first_round.status = "active"
                session.add(first_round)