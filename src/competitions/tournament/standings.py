# competitions/tournament/standings.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from sqlmodel import select
from datetime import datetime
import uuid
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
from competitions.models.tournaments import Tournament
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.rounds import Round, RoundType
from teams.models import Team
from matches.service import MatchService
from .schemas import TournamentTeam, TournamentStandings

class StandingsCalculator(ABC):
    """Base class for tournament standings calculation"""
    
    @abstractmethod
    async def calculate_standings(
        self,
        tournament: Tournament,
        match_service: MatchService,
        session
    ) -> TournamentStandings:
        """Calculate tournament standings"""
        pass
    
    async def _get_round_fixtures(
        self,
        round_id: uuid.UUID,
        session
    ) -> List[Fixture]:
        """Get fixtures for a round"""
        stmt = select(Fixture).where(Fixture.round_id == round_id)
        result = (await session.execute(stmt)).scalars()
        return result.all()

class RegularStandingsCalculator(StandingsCalculator):
    """Calculator for regular (group stage) tournament standings"""
    
    async def calculate_standings(
        self,
        tournament: Tournament,
        session: AsyncSession
    ) -> TournamentStandings:
        # Get all fixtures
        stmt = select(Fixture).where(
            Fixture.tournament_id == tournament.id
        ).options(
            selectinload(Fixture.results)
        )
        result = await session.execute(stmt)
        fixtures = result.scalars().all()
        
        # Track team stats
        team_stats: Dict[uuid.UUID, Dict[str, int]] = {}
        
        # Process each fixture
        for fixture in fixtures:
            team_1 = fixture.team_1
            team_2 = fixture.team_2
            
            # Initialize team stats if needed
            for team_id in [team_1, team_2]:
                if team_id not in team_stats:
                    team_stats[team_id] = {
                        'matches_played': 0,
                        'matches_won': 0,
                        'matches_lost': 0,
                        'points': 0,
                    }
            
            # Process completed or forfeited fixtures only
            if fixture.status in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]:
                team_stats[team_1]['matches_played'] += 1
                team_stats[team_2]['matches_played'] += 1
                
                winner_id = await fixture.get_winner_id(session)
                if winner_id:
                    # Update winner stats
                    team_stats[winner_id]['matches_won'] += 1
                    team_stats[winner_id]['points'] += 3
                    
                    # Update loser stats
                    loser_id = team_2 if winner_id == team_1 else team_1
                    team_stats[loser_id]['matches_lost'] += 1
                
        # Convert to TeamStanding objects
        teams = []
        for team_id, stats in team_stats.items():
            teams.append(TournamentTeam(
                team_id=team_id,
                matches_played=stats['matches_played'],
                matches_won=stats['matches_won'], 
                matches_lost=stats['matches_lost'],
                points=stats['points'],
                status="active"
            ))
        
        # Sort by points, then wins
        teams.sort(key=lambda x: (-x.points, -x.matches_won))
        
        return TournamentStandings(
            tournament_id=tournament.id,
            round=None,  # Not relevant for regular standings
            teams=teams,
            last_updated=datetime.now()
        )

class KnockoutStandingsCalculator(StandingsCalculator):
    """Calculator for knockout tournament standings"""
    
    async def calculate_standings(
        self,
        tournament: Tournament,
        session: AsyncSession
    ) -> TournamentStandings:
        # Get all rounds in order
        stmt = select(Round).where(
            Round.tournament_id == tournament.id
        ).order_by(Round.round_number)
        result = await session.execute(stmt)
        rounds = result.scalars().all()
        
        # Track teams and their progress
        team_stats: Dict[uuid.UUID, Dict[str, int]] = {}
        eliminated_in_round: Dict[int, List[uuid.UUID]] = {}
        
        # Process each round
        for round in rounds:
            fixtures = await self._get_round_fixtures(round.id, session)
            
            for fixture in fixtures:
                # Initialize team stats
                for team_id in [fixture.team_1, fixture.team_2]:
                    if team_id not in team_stats:
                        team_stats[team_id] = {
                            'matches_played': 0,
                            'matches_won': 0,
                            'matches_lost': 0,
                            'final_position': None,
                            'eliminated_round': None
                        }
                
                # Only process completed fixtures
                if fixture.status in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]:
                    team_stats[fixture.team_1]['matches_played'] += 1
                    team_stats[fixture.team_2]['matches_played'] += 1
                    
                    winner_id = await fixture.get_winner_id(session)
                    if winner_id:
                        # Update winner
                        team_stats[winner_id]['matches_won'] += 1
                        
                        # Update loser
                        loser_id = fixture.team_2 if winner_id == fixture.team_1 else fixture.team_1
                        team_stats[loser_id]['matches_lost'] += 1
                        
                        # Track elimination
                        if round.round_number not in eliminated_in_round:
                            eliminated_in_round[round.round_number] = []
                        eliminated_in_round[round.round_number].append(loser_id)
        
        # Calculate final positions
        current_position = 1
        total_teams = len(team_stats)
        
        # Winner (reached final and won)
        final_round = rounds[-1]
        final_fixtures = await self._get_round_fixtures(final_round.id, session)
        if final_fixtures:
            winner_id = await final_fixtures[0].get_winner_id(session)
            if winner_id:
                team_stats[winner_id]['final_position'] = current_position
                current_position += 1
                
                # Runner up
                runner_up = final_fixtures[0].team_2 if winner_id == final_fixtures[0].team_1 else final_fixtures[0].team_1
                team_stats[runner_up]['final_position'] = current_position
                current_position += 1
        
        # Eliminated teams by round (latest rounds first)
        for round_num in sorted(eliminated_in_round.keys(), reverse=True):
            eliminated_teams = eliminated_in_round[round_num]
            for team_id in eliminated_teams:
                if team_stats[team_id]['final_position'] is None:
                    team_stats[team_id]['final_position'] = current_position
                    current_position += 1
        
        # Convert to TeamStanding objects
        teams = []
        for team_id, stats in team_stats.items():
            status = "eliminated"
            if stats['final_position'] == 1:
                status = "winner"
            elif stats['final_position'] == 2:
                status = "runner_up"
            elif stats['matches_played'] < stats['matches_won'] + stats['matches_lost']:
                status = "active"
                
            teams.append(TournamentTeam(
                team_id=team_id,
                matches_played=stats['matches_played'],
                matches_won=stats['matches_won'],
                matches_lost=stats['matches_lost'],
                points=0,  # Not used in knockout
                status=status,
                final_position=stats['final_position']
            ))
            
        # Sort by final position
        teams.sort(key=lambda x: (x.final_position or total_teams + 1))
        
        return TournamentStandings(
            tournament_id=tournament.id,
            round=len(rounds),
            teams=teams,
            last_updated=datetime.now()
        )

def get_standings_calculator(tournament_type: str) -> StandingsCalculator:
    """Factory function to get appropriate standings calculator"""
    calculators = {
        'regular': RegularStandingsCalculator(),
        'knockout': KnockoutStandingsCalculator()
    }
    
    calculator = calculators.get(tournament_type.lower())
    if not calculator:
        raise ValueError(f"No standings calculator for tournament type: {tournament_type}")
    
    return calculator