from typing import List
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
import uuid
from sqlmodel.ext.asyncio.session import AsyncSession
from competitions.models.tournaments import Tournament, TournamentType, TournamentState
from competitions.models.rounds import Round, RoundType
from competitions.models.fixtures import Fixture, FixtureStatus
from teams.models import Team
from matches.models import Result, ConfirmationStatus
from auth.models import Player

class TestDataBuilder:
    """Helper class to build test data with consistent relationships"""
    
    def __init__(self):
        self.teams = []
        self.players = []
        self.tournaments = []
        self.rounds = []
        self.fixtures = []
        self.results = []
        
    async def create_teams(self, count: int, session: AsyncSession) -> List[Team]:
        """Create a specified number of test teams"""
        teams = []
        for i in range(count):
            team = Team(
                name=f"Team {i+1}",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(team)
            teams.append(team)
        await session.commit()
        for team in teams:
            await session.refresh(team)
        self.teams.extend(teams)
        return teams

    async def create_regular_tournament(
        self,
        team_count: int,
        session: AsyncSession
    ) -> Tournament:
        """Create a regular tournament with basic configuration"""
        tournament = Tournament(
            name="Test Regular Tournament",
            type=TournamentType.REGULAR,
            state=TournamentState.REGISTRATION_CLOSED,
            min_teams=4,
            max_teams=16,
            max_team_size=7,
            min_team_size=5,
            format_config={
                'group_size': team_count,
                'teams_per_group': team_count,
                'teams_advancing': -1,
                'match_format': 'bo3'
            },
            registration_start=datetime.now() - timedelta(days=30),
            registration_end=datetime.now() - timedelta(days=7),
            scheduled_start_date=datetime.now() + timedelta(days=7),
            scheduled_end_date=datetime.now() + timedelta(days=30),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            map_pool=[]  # Add map IDs as needed
        )
        session.add(tournament)
        await session.commit()
        await session.refresh(tournament)
        self.tournaments.append(tournament)
        return tournament
        
    async def create_knockout_tournament(
        self,
        team_count: int,
        session: AsyncSession
    ) -> Tournament:
        """Create a knockout tournament with basic configuration"""
        tournament = Tournament(
            name="Test Knockout Tournament",
            type=TournamentType.KNOCKOUT,
            state=TournamentState.REGISTRATION_CLOSED,
            min_teams=4,
            max_teams=16,
            max_team_size=7,
            min_team_size=5,
            format_config={
                'seeding_type': 'random',
                'third_place_playoff': False,
                'match_format': 'bo3'
            },
            registration_start=datetime.now() - timedelta(days=30),
            registration_end=datetime.now() - timedelta(days=7),
            scheduled_start_date=datetime.now() + timedelta(days=7),
            scheduled_end_date=datetime.now() + timedelta(days=30),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            map_pool=[]  # Add map IDs as needed
        )
        session.add(tournament)
        await session.commit()
        await session.refresh(tournament)
        self.tournaments.append(tournament)
        return tournament

    async def create_round(
        self,
        tournament: Tournament,
        round_number: int,
        round_type: RoundType,
        status: str,
        session: AsyncSession
    ) -> Round:
        """Create a tournament round"""
        round = Round(
            tournament_id=tournament.id,
            round_number=round_number,
            type=round_type,
            status=status,
            start_date=tournament.scheduled_start_date + timedelta(days=(round_number-1)*7),
            end_date=tournament.scheduled_start_date + timedelta(days=round_number*7),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(round)
        await session.commit()
        await session.refresh(round)
        self.rounds.append(round)
        return round
    async def create_fixture (
        self,
        tournament: Tournament,
        round: Round,
        team_1: Team,
        team_2: Team,
        status: FixtureStatus,
        session: AsyncSession
    ) -> Fixture:
        """Create a fixture for a tournament round"""
        fixture = Fixture(
            tournament_id=tournament.id,
            round_id=round.id,
            team_1=team_1.id,
            team_2=team_2.id,
            match_format="bo1",
            scheduled_at=round.start_date + timedelta(days=1),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(fixture)
        await session.commit()
        await session.refresh(fixture)
        self.fixtures.append(fixture)
        return fixture
    

@pytest_asyncio.fixture
def test_data_builder():
    """Fixture providing test data builder"""
    return TestDataBuilder()

@pytest_asyncio.fixture
async def regular_tournament_setup(
    test_data_builder: TestDataBuilder,
    session: AsyncSession
):
    """Setup a regular tournament with teams"""
    teams = await test_data_builder.create_teams(8, session)
    tournament = await test_data_builder.create_regular_tournament(
        len(teams),
        session
    )
    
    return {
        'tournament': tournament,
        'teams': teams,
        'builder': test_data_builder
    }

@pytest_asyncio.fixture
async def knockout_tournament_setup(
    test_data_builder: TestDataBuilder,
    session: AsyncSession
):
    """Setup a knockout tournament with teams"""
    teams = await test_data_builder.create_teams(8, session)
    tournament = await test_data_builder.create_knockout_tournament(
        len(teams),
        session
    )
    
    return {
        'tournament': tournament,
        'teams': teams,
        'builder': test_data_builder
    }