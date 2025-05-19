# competitions/rounds/round_winner_service.py
from typing import List
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from competitions.base_schemas import FixtureStatus
from competitions.models.fixtures import Fixture
from competitions.models.rounds import Round
from teams.models import Team


class RoundWinnerService:
    """Service to determine round winners - extracted from TournamentService
    to avoid circular dependencies in status transitions"""
    
    async def get_round_winners(
        self,
        round: Round,
        session: AsyncSession
    ) -> List[Team]:
        """Get winning teams from completed fixtures in a round"""
        # Get all fixtures for the round
        stmt = select(Fixture).where(Fixture.round_id == round.id)
        result = await session.execute(stmt)
        fixtures = result.scalars().all()
        
        # For completed/forfeited fixtures, get winners
        winners = []
        for fixture in fixtures:
            if fixture.status not in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]:
                raise ValueError(
                    f"Not all fixtures are completed in round {round.round_number}"
                )
                
            winner_id = await fixture.get_winner_id(session)
            if not winner_id:
                raise ValueError(
                    f"No winner determined for completed fixture {fixture.id}"
                )
                
            winner = await session.get(Team, winner_id)
            winners.append(winner)
            
        return winners