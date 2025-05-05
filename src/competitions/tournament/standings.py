# competitions/tournament/standings.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from sqlmodel import select
from datetime import datetime
import uuid
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
from competitions.models.tournaments import Tournament, TournamentType, TournamentRegistration, RegistrationStatus
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.rounds import Round
from matches.models import Result
from teams.models import Team
from .schemas import TournamentTeam, TournamentStandings
from services.match import match_service
class StandingsCalculator(ABC):
    """Abstract base class for tournament standings calculation"""
    
    @abstractmethod
    async def calculate_standings(
        self,
        tournament: Tournament,
        session: AsyncSession
    ) -> TournamentStandings:
        """Calculate tournament standings"""
        pass
    
    async def _get_round_fixtures(
        self,
        round_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Fixture]:
        """Get fixtures for a round"""
        stmt = select(Fixture).where(Fixture.round_id == round_id)
        result = await session.execute(stmt)
        return result.scalars().all()
        
    async def _get_match_results(
        self,
        fixture_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Result]:
        """Get match results for a fixture"""
        return await match_service.get_match_results(fixture_id, session)

    async def _get_registered_teams(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Team]:
        """Get all registered teams for a tournament"""
        stmt = select(Team).join(
            TournamentRegistration,
            TournamentRegistration.team_id == Team.id
        ).where(
            TournamentRegistration.tournament_id == tournament_id,
            TournamentRegistration.status == RegistrationStatus.APPROVED
        )
        result = await session.execute(stmt)
        return result.scalars().all()
        
    @staticmethod
    def get_calculator(tournament_type: TournamentType) -> 'StandingsCalculator':
        """Factory method to get appropriate standings calculator"""
        calculators = {
            TournamentType.REGULAR: RegularStandingsCalculator(),
            TournamentType.KNOCKOUT: KnockoutStandingsCalculator()
        }
        
        calculator = calculators.get(tournament_type)
        if not calculator:
            raise ValueError(f"No standings calculator for tournament type: {tournament_type}")
        
        return calculator

def get_standings_calculator(tournament_type: TournamentType):
    return StandingsCalculator().get_calculator(tournament_type)

class RegularStandingsCalculator(StandingsCalculator):
    """Calculator for regular (round-robin/league) tournament standings"""
    
    async def calculate_standings(
        self,
        tournament: Tournament,
        session: AsyncSession
    ) -> TournamentStandings:
        # Get all fixtures for the tournament
        stmt = select(Fixture).where(
            Fixture.tournament_id == tournament.id
        ).options(
            selectinload(Fixture.results)
        )
        result = await session.execute(stmt)
        fixtures = result.scalars().all()
        
        # Get all registered teams
        teams = await self._get_registered_teams(tournament.id, session)
        
        # Initialize team stats
        team_stats: Dict[uuid.UUID, Dict[str, int]] = {}
        for team in teams:
            team_stats[team.id] = {
                'matches_played': 0,
                'matches_won': 0,
                'matches_lost': 0,
                'points': 0
            }
        
        # Process each fixture
        for fixture in fixtures:
            if fixture.status in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]:
                team_1_id = fixture.team_1
                team_2_id = fixture.team_2
                
                # Make sure both teams are in our stats
                if team_1_id in team_stats and team_2_id in team_stats:
                    team_stats[team_1_id]['matches_played'] += 1
                    team_stats[team_2_id]['matches_played'] += 1
                    
                    # Determine winner
                    if fixture.status == FixtureStatus.FORFEITED:
                        winner_id = fixture.forfeit_winner
                    else:
                        # Get match results to determine winner
                        results = await match_service.get_match_results(fixture.id, session)
                        winner_id = await self._determine_fixture_winner(fixture, results)
                    
                    if winner_id:
                        # Update winner stats
                        team_stats[winner_id]['matches_won'] += 1
                        team_stats[winner_id]['points'] += 3  # Standard 3 points for a win
                        
                        # Update loser stats
                        loser_id = team_2_id if winner_id == team_1_id else team_1_id
                        team_stats[loser_id]['matches_lost'] += 1
                    else:
                        # Draw (if your system supports it)
                        team_stats[team_1_id]['points'] += 1
                        team_stats[team_2_id]['points'] += 1
        
        # Convert to TournamentTeam objects
        tournament_teams = []
        for team_id, stats in team_stats.items():
            tournament_teams.append(TournamentTeam(
                team_id=team_id,
                matches_played=stats['matches_played'],
                matches_won=stats['matches_won'],
                matches_lost=stats['matches_lost'],
                points=stats['points'],
                status="active"
            ))
        
        # Sort by points, then wins, then goal difference if available
        tournament_teams.sort(key=lambda x: (-x.points, -x.matches_won))
        
        # Get current round number
        stmt = select(Round).where(
            Round.tournament_id == tournament.id,
            Round.status == "active"
        )
        result = await session.execute(stmt)
        active_round = result.scalar_one_or_none()
        current_round = active_round.round_number if active_round else None
        
        return TournamentStandings(
            tournament_id=tournament.id,
            round=current_round,
            teams=tournament_teams,
            last_updated=datetime.now()
        )
    
    async def _determine_fixture_winner(
        self,
        fixture: Fixture,
        results: List[Any]
    ) -> Optional[uuid.UUID]:
        """Determine the winner of a fixture based on match results"""
        if not results:
            return None
            
        team_1_wins = 0
        team_2_wins = 0
        
        for result in results:
            if hasattr(result, 'winner_id') and result.winner_id:
                if result.winner_id == fixture.team_1:
                    team_1_wins += 1
                elif result.winner_id == fixture.team_2:
                    team_2_wins += 1
        
        if team_1_wins > team_2_wins:
            return fixture.team_1
        elif team_2_wins > team_1_wins:
            return fixture.team_2
        else:
            return None  # Draw

class KnockoutStandingsCalculator(StandingsCalculator):
    """Calculator for knockout tournament standings"""
    
    async def calculate_standings(
        self,
        tournament: Tournament,
        session: AsyncSession
    ) -> TournamentStandings:
        # Get all rounds sorted by round number
        stmt = select(Round).where(
            Round.tournament_id == tournament.id
        ).order_by(Round.round_number)
        result = await session.execute(stmt)
        rounds = result.scalars().all()
        
        # Get all registered teams
        teams = await self._get_registered_teams(tournament.id, session)
        
        # Initialize team stats
        team_stats: Dict[uuid.UUID, Dict[str, Any]] = {}
        for team in teams:
            team_stats[team.id] = {
                'matches_played': 0,
                'matches_won': 0,
                'matches_lost': 0,
                'points': 0,  # Not typically used in knockout
                'status': 'active',
                'final_position': None,
                'eliminated_round': None
            }
        
        # Track eliminated teams by round
        eliminated_by_round: Dict[int, List[uuid.UUID]] = {}
        
        # Process each round
        for round in rounds:
            fixtures = await self._get_round_fixtures(round.id, session)
            
            for fixture in fixtures:
                if fixture.status in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]:
                    team_1_id = fixture.team_1
                    team_2_id = fixture.team_2
                    
                    if team_1_id in team_stats and team_2_id in team_stats:
                        team_stats[team_1_id]['matches_played'] += 1
                        team_stats[team_2_id]['matches_played'] += 1
                        
                        # Determine winner
                        if fixture.status == FixtureStatus.FORFEITED:
                            winner_id = fixture.forfeit_winner
                        else:
                            results = await match_service.get_match_results(fixture.id, session)
                            winner_id = await self._determine_fixture_winner(fixture, results)
                        
                        if winner_id:
                            # Update winner
                            team_stats[winner_id]['matches_won'] += 1
                            
                            # Update loser
                            loser_id = team_2_id if winner_id == team_1_id else team_1_id
                            team_stats[loser_id]['matches_lost'] += 1
                            team_stats[loser_id]['status'] = 'eliminated'
                            team_stats[loser_id]['eliminated_round'] = round.round_number
                            
                            # Track elimination
                            if round.round_number not in eliminated_by_round:
                                eliminated_by_round[round.round_number] = []
                            eliminated_by_round[round.round_number].append(loser_id)
        
        # Calculate final positions
        current_position = 1
        
        # Find the winner (if tournament is complete)
        final_round = rounds[-1] if rounds else None
        if final_round and final_round.status == "completed":
            final_fixtures = await self._get_round_fixtures(final_round.id, session)
            if final_fixtures:
                final_fixture = final_fixtures[0]
                winner_id = await fixture.get_winner_id(session)
                if winner_id:
                    team_stats[winner_id]['final_position'] = current_position
                    team_stats[winner_id]['status'] = 'winner'
                    current_position += 1
                    
                    # Runner-up
                    runner_up_id = final_fixture.team_2 if winner_id == final_fixture.team_1 else final_fixture.team_1
                    team_stats[runner_up_id]['final_position'] = current_position
                    team_stats[runner_up_id]['status'] = 'runner_up'
                    current_position += 1
        
        # Assign positions to eliminated teams (latest rounds first)
        for round_num in sorted(eliminated_by_round.keys(), reverse=True):
            eliminated_teams = eliminated_by_round[round_num]
            for team_id in eliminated_teams:
                if team_stats[team_id]['final_position'] is None:
                    team_stats[team_id]['final_position'] = current_position
            current_position += len(eliminated_teams)
        
        # Convert to TournamentTeam objects
        tournament_teams = []
        for team_id, stats in team_stats.items():
            tournament_teams.append(TournamentTeam(
                team_id=team_id,
                matches_played=stats['matches_played'],
                matches_won=stats['matches_won'],
                matches_lost=stats['matches_lost'],
                points=stats['points'],
                status=stats['status']
            ))
        
        # Sort by final position
        tournament_teams.sort(key=lambda x: (
            x.final_position if hasattr(x, 'final_position') and x.final_position else float('inf')
        ))
        
        # Get current round
        stmt = select(Round).where(
            Round.tournament_id == tournament.id,
            Round.status == "active"
        )
        result = await session.execute(stmt)
        active_round = result.scalar_one_or_none()
        current_round = active_round.round_number if active_round else len(rounds)
        
        return TournamentStandings(
            tournament_id=tournament.id,
            round=current_round,
            teams=tournament_teams,
            last_updated=datetime.now()
        )
    
    async def _determine_fixture_winner(
        self,
        fixture: Fixture,
        results: List[Any]
    ) -> Optional[uuid.UUID]:
        """Determine the winner of a fixture based on match results"""
        if not results:
            return None
            
        team_1_wins = 0
        team_2_wins = 0
        
        for result in results:
            if hasattr(result, 'winner_id') and result.winner_id:
                if result.winner_id == fixture.team_1:
                    team_1_wins += 1
                elif result.winner_id == fixture.team_2:
                    team_2_wins += 1
        
        # In knockout, there must be a winner
        if team_1_wins > team_2_wins:
            return fixture.team_1
        elif team_2_wins > team_1_wins:
            return fixture.team_2
        else:
            # This shouldn't happen in knockout tournaments
            # You might want to implement a tiebreaker here
            return None