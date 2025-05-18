# status/transition_steps/round.py
from datetime import datetime
import logging
from typing import Any, Dict, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from competitions.models.fixtures import Fixture
from competitions.models.rounds import Round
from competitions.models.tournaments import Tournament, TournamentType
from status.pipeline import TransitionStep

LOG = logging.getLogger('uvicorn.error')

class RoundCompleteStep(TransitionStep):
    """Pipeline step to handle round completion and potential tournament progression"""
    
    async def execute(
        self,
        entity: Round,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != "completed":
            return
        
        # Get tournament
        tournament = await session.get(Tournament, entity.tournament_id)
        if not tournament:
            LOG.error(f"Tournament {entity.tournament_id} not found for round {entity.id}")
            return
        
        # Get next round
        stmt = select(Round).where(
            Round.tournament_id == entity.tournament_id,
            Round.round_number == entity.round_number + 1
        )
        result = await session.execute(stmt)
        next_round = result.scalar_one_or_none()
        
        if next_round:
            # Activate next round
            LOG.info(f"Activating next round {next_round.round_number} for tournament {tournament.id}")
            next_round.status = "active"
            next_round.updated_at = datetime.now()
            session.add(next_round)
            
            # Generate fixtures for knockout tournaments
            if tournament.type == TournamentType.KNOCKOUT:
                from competitions.tournament.service import TournamentService
                tournament_service: TournamentService = context.get('tournament_service')
                
                if tournament_service:
                    # Get winners from completed round
                    winning_teams = await tournament_service.get_round_winners(entity, session)
                    
                    if len(winning_teams) >= 2:
                        # Generate fixtures for next round
                        from competitions.tournament.generation.strategies import get_generation_strategy
                        strategy = get_generation_strategy(tournament.type)
                        fixtures = await strategy.generate_fixtures(
                            tournament,
                            next_round,
                            winning_teams,
                            session
                        )
                        session.add_all(fixtures)
                    else:
                        # Tournament should be completed - trigger completion
                        LOG.info(f"Tournament {tournament.id} should be completed - final round")
        else:
            # No more rounds - tournament might need completion
            LOG.info(f"No more rounds for tournament {tournament.id} after round {entity.round_number}")