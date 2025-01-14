# competitions/tournament/generation/strategies.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import uuid

from competitions.models.tournaments import Tournament, TournamentType
from competitions.models.rounds import Round, RoundType
from competitions.models.fixtures import Fixture, FixtureStatus
from teams.models import Team

class GenerationError(Exception):
    """Base exception for tournament generation errors"""
    pass

class TournamentGenerationStrategy(ABC):
    """Abstract base class for tournament generation strategies"""
    
    @abstractmethod
    async def generate_rounds(
        self,
        tournament: Tournament,
        teams: List[Team],
        session
    ) -> List[Round]:
        """Generate tournament rounds"""
        pass

    @abstractmethod
    async def generate_fixtures(
        self,
        tournament: Tournament,
        round: Round,
        teams: List[Team],
        session
    ) -> List[Fixture]:
        """Generate fixtures for a round"""
        pass

    def _validate_team_count(self, teams: List[Team], min_teams: int, max_teams: int):
        """Validate team count is within bounds"""
        if len(teams) < min_teams:
            raise GenerationError(f"Need at least {min_teams} teams")
        if len(teams) > max_teams:
            raise GenerationError(f"Cannot have more than {max_teams} teams")

class RoundRobinStrategy(TournamentGenerationStrategy):
    """Strategy for generating round-robin group stage tournaments"""
    
    async def generate_rounds(
        self,
        tournament: Tournament,
        teams: List[Team],
        session
    ) -> List[Round]:
        """Generate rounds for round-robin tournament"""
        self._validate_team_count(teams, tournament.min_teams, tournament.max_teams)
        
        num_teams = len(teams)
        num_rounds = (num_teams - 1) * 2  # Each team plays each other twice (home/away)
        rounds = []
        
        # Calculate dates and spacing
        days_between_rounds = 7  # One week between rounds
        round_start = tournament.scheduled_start_date
        
        for round_num in range(num_rounds):
            round = Round(
                tournament_id=tournament.id,
                round_number=round_num + 1,
                type=RoundType.GROUP_STAGE,
                start_date=round_start + timedelta(days=round_num * days_between_rounds),
                end_date=round_start + timedelta(days=(round_num + 1) * days_between_rounds),
                status="pending"
            )
            rounds.append(round)
            
        return rounds

    async def generate_fixtures(
        self,
        tournament: Tournament,
        round: Round,
        teams: List[Team],
        session
    ) -> List[Fixture]:
        """Generate fixtures for a round-robin round"""
        num_teams = len(teams)
        fixtures = []
        
        # Clone teams list and add bye if odd number
        playing_teams = teams.copy()
        if num_teams % 2 != 0:
            playing_teams.append(None)  # Add bye
            
        # Generate pairings using circle method
        half = len(playing_teams) // 2
        round_pairings = list(zip(playing_teams[:half], playing_teams[half:]))
        
        # Rotate teams (keep first team fixed)
        playing_teams = [playing_teams[0]] + [playing_teams[-1]] + playing_teams[1:-1]
        
        # Create fixtures for valid pairings (excluding byes)
        for team_1, team_2 in round_pairings:
            if team_1 is not None and team_2 is not None:
                fixture = Fixture(
                    tournament_id=tournament.id,
                    round_id=round.id,
                    team_1=team_1.id,
                    team_2=team_2.id,
                    match_format=tournament.format_config.get('match_format', 'bo1'),
                    scheduled_at=round.start_date,
                    status=FixtureStatus.SCHEDULED
                )
                fixtures.append(fixture)
                
        return fixtures

class SingleEliminationStrategy(TournamentGenerationStrategy):
    """Strategy for generating single elimination knockout tournaments"""
    
    async def generate_rounds(
        self,
        tournament: Tournament,
        teams: List[Team],
        session
    ) -> List[Round]:
        """Generate rounds for single elimination tournament"""
        self._validate_team_count(teams, tournament.min_teams, tournament.max_teams)
        
        # Calculate number of rounds needed
        num_teams = len(teams)
        num_rounds = (num_teams - 1).bit_length()  # Log2 ceiling
        rounds = []
        
        # Calculate dates and spacing
        days_between_rounds = 7
        round_start = tournament.scheduled_start_date
        
        for round_num in range(num_rounds):
            round = Round(
                tournament_id=tournament.id,
                round_number=round_num + 1,
                type=RoundType.KNOCKOUT,
                start_date=round_start + timedelta(days=round_num * days_between_rounds),
                end_date=round_start + timedelta(days=(round_num + 1) * days_between_rounds),
                status="pending"
            )
            rounds.append(round)
            
        return rounds

    async def generate_fixtures(
        self,
        tournament: Tournament,
        round: Round,
        teams: List[Team],
        session
    ) -> List[Fixture]:
        """Generate fixtures for a knockout round"""
        fixtures = []
        num_teams = len(teams)
        
        # First round may need byes
        if round.round_number == 1:
            # Calculate byes needed to reach perfect power of 2
            target_size = 1 << (num_teams - 1).bit_length()
            num_byes = target_size - num_teams
            
            # Create fixtures with byes
            for i in range(0, num_teams, 2):
                if i < num_byes:
                    # Team gets a bye
                    continue
                
                team_1 = teams[i]
                team_2 = teams[i + 1] if i + 1 < num_teams else None
                
                fixture = Fixture(
                    tournament_id=tournament.id,
                    round_id=round.id,
                    team_1=team_1.id,
                    team_2=team_2.id if team_2 else None,
                    match_format=tournament.format_config.get('match_format', 'bo3'),
                    scheduled_at=round.start_date,
                    status=FixtureStatus.SCHEDULED
                )
                fixtures.append(fixture)
        
        return fixtures

def get_generation_strategy(tournament_type: TournamentType) -> TournamentGenerationStrategy:
    """Factory function to get appropriate generation strategy"""
    strategies = {
        TournamentType.REGULAR: RoundRobinStrategy(),
        TournamentType.KNOCKOUT: SingleEliminationStrategy()
    }
    
    strategy = strategies.get(tournament_type)
    if not strategy:
        raise ValueError(f"No generation strategy for tournament type: {tournament_type}")
    
    return strategy