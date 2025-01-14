"""Test data generation utilities for CS2 10mans system."""

import random
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import asyncio
import pytest_asyncio
import logging
from faker import Faker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Player, AuthType, VerificationStatus
from teams.models import Team, TeamCaptain, Roster
from competitions.models.seasons import Season, SeasonState
from competitions.models.tournaments import Tournament, TournamentType, TournamentState
from competitions.models.rounds import Round, RoundType
from competitions.models.fixtures import Fixture, FixtureStatus
from matches.models import Result, ConfirmationStatus, MatchFormat
from maps.models import Map

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Faker
fake = Faker()

class TestDataConfig:
    """Configuration for test data generation"""
    MIN_ELO = 800
    MAX_ELO = 2000
    MIN_PLAYERS_PER_TEAM = 5
    MAX_PLAYERS_PER_TEAM = 7
    STEAM_ID_PREFIX = "7656119"  # Standard Steam64 ID prefix
    DEFAULT_MAP_POOL = [
        "de_ancient", "de_inferno", "de_mirage", 
        "de_nuke", "de_overpass", "de_vertigo"
    ]
    ROUND_INTERVAL_DAYS = 7

class TestDataBuilder:
    """Helper class to build test data with consistent relationships"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.players: List[Player] = []
        self.teams: List[Team] = []
        self.maps: List[Map] = []
        self.season: Optional[Season] = None
        self.tournament: Optional[Tournament] = None
        self.rounds: List[Round] = []
        self.fixtures: List[Fixture] = []
        self.results: List[Result] = []

    async def generate_all(
        self,
        num_players: int = 50,
        num_teams: int = 8,
        include_season: bool = True
    ):
        """Generate a complete test dataset"""
        logger.info("Starting test data generation...")
        
        await self.generate_maps()
        await self.generate_players(num_players)
        await self.generate_teams(num_teams)
        
        if include_season:
            await self.generate_season()
            await self.generate_tournament()
        
        logger.info("Test data generation completed")

    async def generate_maps(self):
        """Generate standard map pool"""
        logger.info("Generating maps...")
        
        for map_name in TestDataConfig.DEFAULT_MAP_POOL:
            map_obj = Map(name=map_name)
            self.session.add(map_obj)
            self.maps.append(map_obj)
        
        await self.session.commit()
        logger.info(f"Generated {len(self.maps)} maps")

    async def generate_players(self, count: int):
        """Generate test players with realistic data"""
        logger.info(f"Generating {count} players...")
        
        for _ in range(count):
            # Generate a random Steam64 ID
            steam_suffix = ''.join(random.choices('0123456789', k=11))
            steam_id = f"{TestDataConfig.STEAM_ID_PREFIX}{steam_suffix}"
            
            player = Player(
                name=fake.user_name(),
                steam_id=steam_id,
                auth_type=AuthType.STEAM,
                current_elo=random.randint(
                    TestDataConfig.MIN_ELO,
                    TestDataConfig.MAX_ELO
                ),
                verification_status=random.choice(list(VerificationStatus)),
                created_at=fake.date_time_between(
                    start_date='-1y',
                    end_date='now'
                )
            )
            
            self.session.add(player)
            self.players.append(player)
        
        await self.session.commit()
        logger.info(f"Generated {len(self.players)} players")

    async def generate_teams(self, count: int):
        """Generate teams with captains and rosters"""
        logger.info(f"Generating {count} teams...")
        
        available_players = self.players.copy()
        random.shuffle(available_players)
        
        for i in range(count):
            # Create team
            team = Team(
                name=f"Team {fake.unique.word().title()}",
                created_at=fake.date_time_between(
                    start_date='-6m',
                    end_date='now'
                )
            )
            self.session.add(team)
            await self.session.flush()
            
            # Assign random number of players
            team_size = random.randint(
                TestDataConfig.MIN_PLAYERS_PER_TEAM,
                min(TestDataConfig.MAX_PLAYERS_PER_TEAM, len(available_players), TestDataConfig.MIN_PLAYERS_PER_TEAM)
            )
            
            # First player becomes captain
            captain = available_players.pop()
            team_captain = TeamCaptain(
                team_id=team.id,
                player_uid=captain.uid
            )
            self.session.add(team_captain)
            
            # Add remaining players
            team_players = [captain]
            for _ in range(team_size - 1):
                if not available_players:
                    break
                player = available_players.pop()
                team_players.append(player)
            
            # Create roster entries if season exists
            if self.season:
                for player in team_players:
                    roster = Roster(
                        team_id=team.id,
                        player_uid=player.uid,
                        season_id=self.season.id,
                        pending=False
                    )
                    self.session.add(roster)
            
            self.teams.append(team)
        
        await self.session.commit()
        logger.info(f"Generated {len(self.teams)} teams")

    async def generate_season(self):
        """Generate a test season"""
        logger.info("Generating season...")
        
        self.season = Season(
            name=f"Season {fake.unique.random_int(min=1, max=10)}",
            state=SeasonState.IN_PROGRESS,
            created_at=datetime.now() - timedelta(days=30)
        )
        self.session.add(self.season)
        await self.session.commit()
        
        logger.info(f"Generated season: {self.season.name}")

    async def generate_tournament(self, tournament_type: TournamentType = TournamentType.REGULAR):
        """Generate a tournament within the current season"""
        if not self.season:
            raise ValueError("Season must be generated before tournament")
            
        logger.info("Generating tournament...")
        
        # Set format config based on type
        if tournament_type == TournamentType.REGULAR:
            format_config = {
                "group_size": len(self.teams),
                "teams_per_group": len(self.teams) // 2,
                "teams_advancing": 4,
                "match_format": "bo3"
            }
        else:  # KNOCKOUT
            format_config = {
                "seeding_type": "random",
                "third_place_playoff": False,
                "match_format": "bo3"
            }
        
        tournament = Tournament(
            season_id=self.season.id,
            name=f"{self.season.name} {'Regular Season' if tournament_type == TournamentType.REGULAR else 'Knockout'}",
            type=tournament_type,
            state=TournamentState.REGISTRATION_CLOSED,
            min_teams=2,
            max_teams=len(self.teams),
            max_team_size=TestDataConfig.MAX_PLAYERS_PER_TEAM,
            min_team_size=TestDataConfig.MIN_PLAYERS_PER_TEAM,
            registration_start=datetime.now() - timedelta(days=25),
            registration_end=datetime.now() - timedelta(days=20),
            scheduled_start_date=datetime.now() - timedelta(days=15),
            scheduled_end_date=datetime.now() + timedelta(days=15),
            format_config=format_config,
            map_pool=[str(map_obj.id) for map_obj in self.maps]
        )
        
        self.session.add(tournament)
        await self.session.commit()
        await self.session.refresh(tournament)
        self.tournament = tournament
        
        logger.info(f"Generated tournament: {tournament.name}")
        
    async def create_round(
        self,
        tournament: Tournament,
        round_number: int, 
        round_type: RoundType,
        status: str,
        start_date: Optional[datetime] = None
    ) -> Round:
        """Create a tournament round"""
        if not start_date:
            start_date = tournament.scheduled_start_date + timedelta(
                days=(round_number-1) * TestDataConfig.ROUND_INTERVAL_DAYS
            )
            
        round = Round(
            tournament_id=tournament.id,
            round_number=round_number,
            type=round_type,
            best_of=3,  # Default to BO3
            status=status,
            start_date=start_date,
            end_date=start_date + timedelta(days=TestDataConfig.ROUND_INTERVAL_DAYS),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.session.add(round)
        await self.session.commit()
        await self.session.refresh(round)
        self.rounds.append(round)
        return round

    async def create_fixture(
        self,
        tournament: Tournament,
        round: Round,
        team_1: Team,
        team_2: Team,
        match_format: MatchFormat = MatchFormat.BO3,
        status: FixtureStatus = FixtureStatus.SCHEDULED,
        scheduled_at: Optional[datetime] = None
    ) -> Fixture:
        """Create a fixture between two teams"""
        if not scheduled_at:
            scheduled_at = round.start_date + timedelta(days=1)
            
        fixture = Fixture(
            tournament_id=tournament.id,
            round_id=round.id,
            team_1=team_1.id,
            team_2=team_2.id,
            match_format=match_format,
            scheduled_at=scheduled_at,
            status=status,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.session.add(fixture)
        await self.session.commit()
        await self.session.refresh(fixture)
        self.fixtures.append(fixture)
        return fixture

    async def create_fixture_with_results(
        self,
        tournament: Tournament,
        round: Round,
        team_1: Team,
        team_2: Team,
        team_1_wins: Optional[int] = None,
        user: Optional[Player] = None
    ) -> Tuple[Fixture, List[Result]]:
        """Create a completed fixture with results"""
        fixture = await self.create_fixture(
            tournament=tournament,
            round=round,
            team_1=team_1,
            team_2=team_2,
            status=FixtureStatus.COMPLETED
        )
        
        # Determine maps needed based on format
        maps_needed = 2 if fixture.match_format == MatchFormat.BO3 else 1
        
        # If team_1_wins not specified, randomly decide winner
        if team_1_wins is None:
            team_1_wins = random.randint(0, maps_needed)
            
        results = []
        for map_number in range(1, maps_needed + 1):
            is_team_1_win = map_number <= team_1_wins
            
            # Generate realistic scores
            if is_team_1_win:
                team_1_score = 16
                team_2_score = random.randint(5, 14)
            else:
                team_1_score = random.randint(5, 14)
                team_2_score = 16
                
            result = await self.create_match_result(
                fixture=fixture,
                team_1_score=team_1_score,
                team_2_score=team_2_score,
                submitting_player=user,
                map_number=map_number
            )
            results.append(result)
            
        return fixture, results

    async def create_match_result(
        self,
        fixture: Fixture,
        team_1_score: int,
        team_2_score: int,
        submitting_player: Optional[Player] = None,
        map_number: int = 1,
        status: ConfirmationStatus = ConfirmationStatus.CONFIRMED,
        map_id: Optional[uuid.UUID] = None
    ) -> Result:
        """Create a match result"""
        # Get a map if none provided
        if not map_id and self.maps:
            map_id = random.choice(self.maps).id
            
        if not map_id:
            raise ValueError("No map ID provided and no maps available")
            
        result = Result(
            fixture_id=fixture.id,
            map_id=map_id,
            map_number=map_number,
            team_1_score=team_1_score,
            team_2_score=team_2_score,
            team_1_side_first=random.choice(['CT', 'T']),
            submitted_by=submitting_player.uid if submitting_player else None,
            confirmation_status=status,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.session.add(result)
        await self.session.commit()
        await self.session.refresh(result)
        self.results.append(result)
        return result

    async def create_forfeited_fixture(
        self,
        tournament: Tournament,
        round: Round,
        team_1: Team,
        team_2: Team,
        forfeit_winner: Team,
        forfeit_reason: str = "Team did not show up"
    ) -> Fixture:
        """Create a forfeited fixture"""
        fixture = await self.create_fixture(
            tournament=tournament,
            round=round,
            team_1=team_1,
            team_2=team_2,
            status=FixtureStatus.FORFEITED
        )
        
        fixture.forfeit_winner = forfeit_winner.id
        fixture.forfeit_reason = forfeit_reason
        
        self.session.add(fixture)
        await self.session.commit()
        await self.session.refresh(fixture)
        
        return fixture
    
@pytest_asyncio.fixture
async def test_data_builder(session: AsyncSession):
    """Fixture providing test data builder"""
    return TestDataBuilder(session)

@pytest_asyncio.fixture
async def regular_tournament_setup(
    test_data_builder: TestDataBuilder,
    session: AsyncSession
):
    """Setup a regular tournament with teams"""
    # Generate base data
    await test_data_builder.generate_maps()
    await test_data_builder.generate_players(40)  # Enough for 8 teams of 5
    await test_data_builder.generate_teams(8)
    await test_data_builder.generate_season()
    await test_data_builder.generate_tournament(tournament_type=TournamentType.REGULAR)
    
    return {
        'tournament': test_data_builder.tournament,
        'teams': test_data_builder.teams,
        'builder': test_data_builder
    }

@pytest_asyncio.fixture
async def knockout_tournament_setup(
    test_data_builder: TestDataBuilder,
    session: AsyncSession
):
    """Setup a knockout tournament with teams"""
    # Generate base data
    await test_data_builder.generate_maps()
    await test_data_builder.generate_players(40)
    await test_data_builder.generate_teams(8)
    await test_data_builder.generate_season()
    await test_data_builder.generate_tournament(tournament_type=TournamentType.KNOCKOUT)
    
    return {
        'tournament': test_data_builder.tournament,
        'teams': test_data_builder.teams,
        'builder': test_data_builder
    }