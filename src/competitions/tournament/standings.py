# competitions/tournament/standings.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from sqlmodel import select
from datetime import datetime
import uuid

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
        result = await session.execute(stmt)
        return result.all()

class RegularStandingsCalculator(StandingsCalculator):
    """Calculator for regular (group stage) tournament standings"""
    
    async def calculate_standings(
        self,
        tournament: Tournament,
        match_service: MatchService,
        session
    ) -> TournamentStandings:
        # Get all group stage rounds
        stmt = select(Round).where(
            Round.tournament_id == tournament.id,
            Round.type == RoundType.GROUP_STAGE
        ).order_by(Round.round_number)
        result = await session.execute(stmt)
        rounds = result.all()
        
        # Initialize team statistics
        team_stats: Dict[uuid.UUID, Dict[str, Any]] = {}
        
        # Process each round
        for round in rounds:
            fixtures = await self._get_round_fixtures(round.id, session)
            for fixture in fixtures:
                if fixture.status not in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]:
                    continue
                    
                await self._process_fixture_result(
                    fixture,
                    match_service,
                    team_stats,
                    session
                )
        
        # Convert stats to team standings
        teams = []
        for team_id, stats in team_stats.items():
            team = await session.get(Team, team_id)
            teams.append(TournamentTeam(
                team_id=team_id,
                team_name=team.name,
                matches_played=stats['matches_played'],
                matches_won=stats['matches_won'],
                matches_lost=stats['matches_lost'],
                points=stats['points'],
                status="active"
            ))
        
        # Sort teams by points and other criteria
        teams.sort(key=lambda x: (
            x.points,
            x.matches_won,
            -x.matches_lost
        ), reverse=True)
        
        return TournamentStandings(
            tournament_id=tournament.id,
            round=None,
            teams=teams,
            last_updated=datetime.now()
        )
    
    async def _process_fixture_result(
        self,
        fixture: Fixture,
        match_service: MatchService,
        team_stats: Dict[uuid.UUID, Dict[str, Any]],
        session
    ):
        """Process a single fixture result"""
        # Initialize team stats if needed
        for team_id in [fixture.team_1, fixture.team_2]:
            if team_id not in team_stats:
                team_stats[team_id] = {
                    'matches_played': 0,
                    'matches_won': 0,
                    'matches_lost': 0,
                    'points': 0
                }
        
        if fixture.status == FixtureStatus.FORFEITED:
            if not fixture.forfeit_winner:
                # Handle mutual forfeit
                for team_id in [fixture.team_1, fixture.team_2]:
                    team_stats[team_id]['matches_played'] += 1
                    team_stats[team_id]['matches_lost'] += 1
            else:
                winner_id = fixture.forfeit_winner
                loser_id = fixture.team_2 if winner_id == fixture.team_1 else fixture.team_1
                
                team_stats[winner_id]['matches_played'] += 1
                team_stats[winner_id]['matches_won'] += 1
                team_stats[winner_id]['points'] += 3
                
                team_stats[loser_id]['matches_played'] += 1
                team_stats[loser_id]['matches_lost'] += 1
        else:
            # Get match result from match service
            match_result = await match_service.get_match_result(fixture.id, session)
            if not match_result:
                return  # Skip if no result available
            
            # Update winner stats
            team_stats[match_result.winner_id]['matches_played'] += 1
            team_stats[match_result.winner_id]['matches_won'] += 1
            team_stats[match_result.winner_id]['points'] += 3
            
            # Update loser stats
            loser_id = fixture.team_2 if match_result.winner_id == fixture.team_1 else fixture.team_1
            team_stats[loser_id]['matches_played'] += 1
            team_stats[loser_id]['matches_lost'] += 1

class KnockoutStandingsCalculator(StandingsCalculator):
    """Calculator for knockout tournament standings"""
    
    async def calculate_standings(
        self,
        tournament: Tournament,
        match_service: MatchService,
        session
    ) -> TournamentStandings:
        # Get all knockout rounds in reverse order
        stmt = select(Round).where(
            Round.tournament_id == tournament.id,
            Round.type == RoundType.KNOCKOUT
        ).order_by(Round.round_number.desc())
        result = await session.execute(stmt)
        rounds = result.all()
        
        # Track team progress and elimination
        placements: Dict[uuid.UUID, Dict[str, Any]] = {}
        current_round = None
        
        # Process each round
        for round in rounds:
            current_round = round
            fixtures = await self._get_round_fixtures(round.id, session)
            
            for fixture in fixtures:
                if fixture.status not in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]:
                    continue
                    
                await self._process_knockout_fixture(
                    fixture,
                    match_service,
                    round.round_number,
                    placements,
                    session
                )
        
        # Convert placements to team standings
        teams = []
        for team_id, data in placements.items():
            team = await session.get(Team, team_id)
            teams.append(TournamentTeam(
                team_id=team_id,
                team_name=team.name,
                matches_played=data['matches_played'],
                matches_won=data['matches_won'],
                matches_lost=data['matches_lost'],
                points=0,
                status=data['status']
            ))
        
        # Sort by round reached and match stats
        teams.sort(key=lambda x: (
            x.matches_won,
            -x.matches_lost,
            x.matches_played
        ), reverse=True)
        
        return TournamentStandings(
            tournament_id=tournament.id,
            round=current_round.round_number if current_round else None,
            teams=teams,
            last_updated=datetime.now()
        )
    
    async def _process_knockout_fixture(
        self,
        fixture: Fixture,
        match_service: MatchService,
        round_number: int,
        placements: Dict[uuid.UUID, Dict[str, Any]],
        session
    ):
        """Process a knockout fixture result"""
        # Initialize team placements
        for team_id in [fixture.team_1, fixture.team_2]:
            if team_id not in placements:
                placements[team_id] = {
                    'matches_played': 0,
                    'matches_won': 0,
                    'matches_lost': 0,
                    'last_round': round_number,
                    'status': 'eliminated'
                }
        
        # Determine winner
        if fixture.status == FixtureStatus.FORFEITED:
            if not fixture.forfeit_winner:
                # Handle mutual forfeit - both teams eliminated
                for team_id in [fixture.team_1, fixture.team_2]:
                    placements[team_id]['matches_played'] += 1
                    placements[team_id]['matches_lost'] += 1
                    placements[team_id]['status'] = 'eliminated'
                return
                
            winner_id = fixture.forfeit_winner
            loser_id = fixture.team_2 if winner_id == fixture.team_1 else fixture.team_1
        else:
            match_result = await match_service.get_match_result(fixture.id, session)
            if not match_result:
                return
                
            winner_id = match_result.winner_id
            loser_id = fixture.team_2 if winner_id == fixture.team_1 else fixture.team_1
        
        # Update winner status
        placements[winner_id]['matches_played'] += 1
        placements[winner_id]['matches_won'] += 1
        placements[winner_id]['last_round'] = round_number
        placements[winner_id]['status'] = 'qualified' if round_number > 1 else 'winner'
        
        # Update loser status
        placements[loser_id]['matches_played'] += 1
        placements[loser_id]['matches_lost'] += 1
        placements[loser_id]['status'] = 'eliminated'

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