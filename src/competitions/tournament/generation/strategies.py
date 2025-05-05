from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import uuid
import random

from competitions.models.tournaments import Tournament, TournamentType
from competitions.models.rounds import Round, RoundType
from competitions.models.fixtures import Fixture, FixtureStatus
from teams.models import Team
from competitions.tournament.standings import StandingsCalculator

class GenerationError(Exception):
    """Base exception for tournament generation errors"""
    pass

class SeedingStrategy(ABC):
    """Abstract base class for seeding strategies"""
    
    @abstractmethod
    async def seed_teams(self, teams: List[Team], tournament: Tournament, session) -> List[Team]:
        """Seed teams according to the strategy"""
        pass

class RandomSeedingStrategy(SeedingStrategy):
    """Random seeding strategy"""
    
    async def seed_teams(self, teams: List[Team], tournament: Tournament, session) -> List[Team]:
        shuffled = teams.copy()
        random.shuffle(shuffled)
        return shuffled

class EloSeedingStrategy(SeedingStrategy):
    """Seed teams based on ELO rating"""
    
    async def seed_teams(self, teams: List[Team], tournament: Tournament, session) -> List[Team]:
        # Get team ELO ratings
        team_elos = {}
        for team in teams:
            # Calculate average team ELO based on active roster
            team_elos[team.id] = await self._calculate_team_elo(team, session)
        
        # Sort teams by ELO
        return sorted(teams, key=lambda t: team_elos[t.id], reverse=True)
    
    async def _calculate_team_elo(self, team: Team, session) -> float:
        # Implementation to calculate average ELO of active roster
        active_roster = [r for r in team.rosters if r.status == 'ACTIVE']
        if not active_roster:
            return 0.0
        
        total_elo = sum(r.player.current_elo or 0 for r in active_roster)
        return total_elo / len(active_roster)

class StandingsSeedingStrategy(SeedingStrategy):
    """Seed teams based on previous tournament standings"""
    
    def __init__(self, source_tournament_id: Optional[uuid.UUID] = None):
        self.source_tournament_id = source_tournament_id
    
    async def seed_teams(self, teams: List[Team], tournament: Tournament, session) -> List[Team]:
        if not self.source_tournament_id:
            # If no source tournament, fall back to random
            return await RandomSeedingStrategy().seed_teams(teams, tournament, session)
        
        # Get standings from source tournament
        standings_calc = StandingsCalculator.get_calculator(tournament.type)
        source_standings = await standings_calc.calculate_standings(
            tournament_id=self.source_tournament_id,
            session=session
        )
        
        # Create ranking map
        team_ranks = {entry.team_id: idx for idx, entry in enumerate(source_standings.teams)}
        
        # Sort teams by their ranking, putting unsorted teams at the end
        return sorted(teams, key=lambda t: team_ranks.get(t.id, len(teams)))

class ManualSeedingStrategy(SeedingStrategy):
    """Manual seeding based on provided seed order"""
    
    def __init__(self, seed_order: Dict[uuid.UUID, int]):
        self.seed_order = seed_order
    
    async def seed_teams(self, teams: List[Team], tournament: Tournament, session) -> List[Team]:
        return sorted(teams, key=lambda t: self.seed_order.get(t.id, float('inf')))

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

    async def seed_teams(
        self,
        teams: List[Team],
        tournament: Tournament,
        session
    ) -> List[Team]:
        """Apply seeding to teams based on configuration"""
        seeding_type = tournament.format_config.get('seeding_type', 'random')
        
        if seeding_type == 'random':
            strategy = RandomSeedingStrategy()
        elif seeding_type == 'elo':
            strategy = EloSeedingStrategy()
        elif seeding_type == 'standings':
            source_id = tournament.format_config.get('source_tournament_id')
            strategy = StandingsSeedingStrategy(source_id)
        elif seeding_type == 'manual':
            seed_order = tournament.format_config.get('seed_order', {})
            strategy = ManualSeedingStrategy(seed_order)
        else:
            raise GenerationError(f"Unknown seeding type: {seeding_type}")
            
        return await strategy.seed_teams(teams, tournament, session)

class RoundRobinStrategy(TournamentGenerationStrategy):
    """Strategy for generating round-robin tournaments"""
    
    async def generate_rounds(
        self,
        tournament: Tournament,
        teams: List[Team],
        session
    ) -> List[Round]:
        """Generate rounds for round-robin tournament"""
        num_teams = len(teams)
        league_format = tournament.league_format
        
        if league_format == 'single_round_robin':
            num_rounds = num_teams - 1 if num_teams % 2 == 0 else num_teams
        elif league_format == 'double_round_robin':
            num_rounds = (num_teams - 1) * 2 if num_teams % 2 == 0 else num_teams * 2
        elif league_format == 'home_away':
            num_rounds = (num_teams - 1) * 2
        else:
            raise GenerationError(f"Unknown league format: {league_format}")
        
        rounds = []
        days_between_rounds = tournament.scheduling_config.get('days_between_rounds', 7)
        round_start = tournament.scheduled_start_date
        
        for round_num in range(num_rounds):
            round = Round(
                tournament_id=tournament.id,
                round_number=round_num + 1,
                type=RoundType.GROUP_STAGE,
                best_of=self._get_match_format_games(tournament.format_config['match_format']),
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
        """Generate fixtures for a round-robin round using circle method"""
        num_teams = len(teams)
        fixtures = []
        
        # Apply seeding if this is the first round
        if round.round_number == 1:
            teams = await self.seed_teams(teams, tournament, session)
        
        # Clone teams list and add bye if odd number
        playing_teams = teams.copy()
        if num_teams % 2 != 0:
            playing_teams.append(None)  # Add bye
            
        # Calculate pairings for this round using circle method
        n = len(playing_teams)
        half = n // 2
        
        # Rotate teams for the specified round number
        round_idx = (round.round_number - 1) % (n - 1)
        fixed = playing_teams[0]
        rotated = playing_teams[1:]
        for _ in range(round_idx):
            rotated = [rotated[-1]] + rotated[:-1]
        playing_teams = [fixed] + rotated
        
        # Generate pairings
        for i in range(half):
            team_1 = playing_teams[i]
            team_2 = playing_teams[n - 1 - i]
            
            if team_1 is not None and team_2 is not None:
                # For double round robin, switch home/away in second half
                if (tournament.league_format == 'double_round_robin' and 
                    round.round_number > (n - 1)):
                    team_1, team_2 = team_2, team_1
                    
                fixture = Fixture(
                    tournament_id=tournament.id,
                    round_id=round.id,
                    team_1=team_1.id,
                    team_2=team_2.id,
                    match_format=tournament.format_config['match_format'],
                    scheduled_at=round.start_date,
                    status=FixtureStatus.SCHEDULED
                )
                fixtures.append(fixture)
                
        return fixtures

    def _get_match_format_games(self, format_str: str) -> int:
        """Convert format string to number of games"""
        formats = {'bo1': 1, 'bo3': 3, 'bo5': 5}
        return formats.get(format_str, 1)

class SingleEliminationStrategy(TournamentGenerationStrategy):
    """Strategy for generating single elimination knockout tournaments"""
    
    async def generate_rounds(
        self,
        tournament: Tournament,
        teams: List[Team],
        session
    ) -> List[Round]:
        """Generate rounds for single elimination tournament"""
        num_teams = len(teams)
        num_rounds = (num_teams - 1).bit_length()  # Log2 ceiling
        rounds = []
        
        days_between_rounds = tournament.scheduling_config.get('days_between_rounds', 7)
        round_start = tournament.scheduled_start_date
        
        round_names = self._get_round_names(num_rounds)
        
        for round_num in range(num_rounds):
            round = Round(
                tournament_id=tournament.id,
                round_number=round_num + 1,
                type=RoundType.KNOCKOUT,
                best_of=self._get_match_format_games(tournament.format_config['match_format']),
                start_date=round_start + timedelta(days=round_num * days_between_rounds),
                end_date=round_start + timedelta(days=(round_num + 1) * days_between_rounds),
                status="pending",
                name=round_names[round_num] if round_num < len(round_names) else f"Round {round_num + 1}"
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
        
        if round.round_number == 1:
            # First round - apply seeding and create initial bracket
            seeded_teams = await self.seed_teams(teams, tournament, session)
            
            # Calculate number of byes needed
            target_size = 1 << (num_teams - 1).bit_length()
            num_byes = target_size - num_teams
            
            # Create fixtures with byes
            for i in range(0, target_size, 2):
                if i < num_byes * 2:
                    # This match gets a bye
                    if i // 2 < len(seeded_teams):
                        # This team advances automatically
                        continue
                
                team_1_idx = i - num_byes
                team_2_idx = target_size - 1 - i + num_byes
                
                if team_1_idx < len(seeded_teams) and team_2_idx < len(seeded_teams):
                    fixture = Fixture(
                        tournament_id=tournament.id,
                        round_id=round.id,
                        team_1=seeded_teams[team_1_idx].id,
                        team_2=seeded_teams[team_2_idx].id,
                        match_format=tournament.format_config['match_format'],
                        scheduled_at=round.start_date,
                        status=FixtureStatus.SCHEDULED
                    )
                    fixtures.append(fixture)
        else:
            # Later rounds - teams provided are winners from previous round
            for i in range(0, len(teams), 2):
                if i + 1 < len(teams):
                    fixture = Fixture(
                        tournament_id=tournament.id,
                        round_id=round.id,
                        team_1=teams[i].id,
                        team_2=teams[i + 1].id,
                        match_format=tournament.format_config['match_format'],
                        scheduled_at=round.start_date,
                        status=FixtureStatus.SCHEDULED
                    )
                    fixtures.append(fixture)
        
        return fixtures

    def _get_round_names(self, num_rounds: int) -> List[str]:
        """Get human-readable round names"""
        names = []
        if num_rounds >= 1:
            names.insert(0, "Finals")
        if num_rounds >= 2:
            names.insert(0, "Semi-Finals")
        if num_rounds >= 3:
            names.insert(0, "Quarter-Finals")
        if num_rounds >= 4:
            names.insert(0, "Round of 16")
        if num_rounds >= 5:
            names.insert(0, "Round of 32")
        if num_rounds >= 6:
            names.insert(0, "Round of 64")
        
        # Fill in remaining rounds
        while len(names) < num_rounds:
            names.insert(0, f"Round {num_rounds - len(names)}")
            
        return names

    def _get_match_format_games(self, format_str: str) -> int:
        """Convert format string to number of games"""
        formats = {'bo1': 1, 'bo3': 3, 'bo5': 5}
        return formats.get(format_str, 1)

class SwissSystemStrategy(TournamentGenerationStrategy):
    """Strategy for generating Swiss system tournaments"""
    
    async def generate_rounds(
        self,
        tournament: Tournament,
        teams: List[Team],
        session
    ) -> List[Round]:
        """Generate rounds for Swiss system tournament"""
        # Number of rounds is typically log2(teams) + 1 or specified in config
        num_teams = len(teams)
        num_rounds = tournament.format_config.get('num_rounds', (num_teams - 1).bit_length() + 1)
        
        rounds = []
        days_between_rounds = tournament.scheduling_config.get('days_between_rounds', 7)
        round_start = tournament.scheduled_start_date
        
        for round_num in range(num_rounds):
            round = Round(
                tournament_id=tournament.id,
                round_number=round_num + 1,
                type=RoundType.GROUP_STAGE,  # Swiss uses group stage type
                best_of=self._get_match_format_games(tournament.format_config['match_format']),
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
        """Generate fixtures for a Swiss system round"""
        if round.round_number == 1:
            # First round uses seeding
            seeded_teams = await self.seed_teams(teams, tournament, session)
            return self._generate_first_round_pairings(tournament, round, seeded_teams)
        else:
            # Later rounds use Swiss pairing based on standings
            return await self._generate_swiss_pairings(tournament, round, teams, session)

    def _generate_first_round_pairings(
        self,
        tournament: Tournament,
        round: Round,
        teams: List[Team]
    ) -> List[Fixture]:
        """Generate first round pairings based on seeding"""
        fixtures = []
        num_teams = len(teams)
        
        # Pair adjacent seeds (1v2, 3v4, etc.)
        for i in range(0, num_teams, 2):
            if i + 1 < num_teams:
                fixture = Fixture(
                    tournament_id=tournament.id,
                    round_id=round.id,
                    team_1=teams[i].id,
                    team_2=teams[i + 1].id,
                    match_format=tournament.format_config['match_format'],
                    scheduled_at=round.start_date,
                    status=FixtureStatus.SCHEDULED
                )
                fixtures.append(fixture)
                
        return fixtures

    async def _generate_swiss_pairings(
        self,
        tournament: Tournament,
        round: Round,
        teams: List[Team],
        session
    ) -> List[Fixture]:
        """Generate Swiss system pairings based on current standings"""
        # Get current standings
        standings_calc = StandingsCalculator.get_calculator(tournament.type)
        standings = await standings_calc.calculate_standings(
            tournament=tournament,
            session=session
        )
        
        # Group teams by score
        score_groups = {}
        for team_standing in standings.teams:
            team = next(t for t in teams if t.id == team_standing.team_id)
            score = team_standing.points
            if score not in score_groups:
                score_groups[score] = []
            score_groups[score].append(team)
        
        # Sort score groups
        sorted_scores = sorted(score_groups.keys(), reverse=True)
        
        fixtures = []
        paired_teams = set()
        previous_matches = await self._get_previous_matches(tournament.id, session)
        
        for score in sorted_scores:
            group = score_groups[score]
            available_teams = [t for t in group if t.id not in paired_teams]
            
            while len(available_teams) >= 2:
                team_1 = available_teams.pop(0)
                paired_teams.add(team_1.id)
                
                # Find best opponent (one they haven't played before)
                team_2 = None
                for candidate in available_teams:
                    if not self._have_played_before(team_1.id, candidate.id, previous_matches):
                        team_2 = candidate
                        break
                
                # If no unplayed opponent, take the first available
                if not team_2:
                    team_2 = available_teams[0]
                
                available_teams.remove(team_2)
                paired_teams.add(team_2.id)
                
                fixture = Fixture(
                    tournament_id=tournament.id,
                    round_id=round.id,
                    team_1=team_1.id,
                    team_2=team_2.id,
                    match_format=tournament.format_config['match_format'],
                    scheduled_at=round.start_date,
                    status=FixtureStatus.SCHEDULED
                )
                fixtures.append(fixture)
        
        # Handle any remaining unpaired team (bye)
        unpaired_teams = [t for t in teams if t.id not in paired_teams]
        if unpaired_teams:
            # Give bye to lowest-ranked unpaired team
            # Implementation depends on how you want to handle byes
            pass
        
        return fixtures

    async def _get_previous_matches(self, tournament_id: uuid.UUID, session) -> List[Tuple[uuid.UUID, uuid.UUID]]:
        """Get all previous matches in the tournament"""
        from sqlmodel import select
        stmt = select(Fixture).where(
            Fixture.tournament_id == tournament_id,
            Fixture.status.in_([FixtureStatus.COMPLETED, FixtureStatus.IN_PROGRESS])
        )
        result = await session.execute(stmt)
        fixtures = result.scalars().all()
        
        return [(f.team_1, f.team_2) for f in fixtures]

    def _have_played_before(
        self,
        team_1_id: uuid.UUID,
        team_2_id: uuid.UUID,
        previous_matches: List[Tuple[uuid.UUID, uuid.UUID]]
    ) -> bool:
        """Check if two teams have played before"""
        for match in previous_matches:
            if (match[0] == team_1_id and match[1] == team_2_id) or \
               (match[0] == team_2_id and match[1] == team_1_id):
                return True
        return False

    def _get_match_format_games(self, format_str: str) -> int:
        """Convert format string to number of games"""
        formats = {'bo1': 1, 'bo3': 3, 'bo5': 5}
        return formats.get(format_str, 1)

def get_generation_strategy(tournament: Tournament) -> TournamentGenerationStrategy:
    """Factory function to get appropriate generation strategy"""
    if tournament.type == TournamentType.REGULAR:
        if tournament.league_format == 'swiss':
            return SwissSystemStrategy()
        else:
            return RoundRobinStrategy()
    elif tournament.type == TournamentType.KNOCKOUT:
        return SingleEliminationStrategy()
    else:
        raise ValueError(f"No generation strategy for tournament type: {tournament.type}")