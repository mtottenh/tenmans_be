"""Test data generation utilities for CS2 10mans system."""

import random
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import asyncio
import logging
from faker import Faker
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Player, AuthType, VerificationStatus
from teams.models import Team, TeamCaptain, Roster
from competitions.models.seasons import Season, SeasonState
from competitions.models.tournaments import Tournament, TournamentType, TournamentState
from competitions.models.fixtures import Fixture, FixtureStatus
from matches.models import Result, ConfirmationStatus
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

class TestDataGenerator:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.players: List[Player] = []
        self.teams: List[Team] = []
        self.maps: List[Map] = []
        self.season: Optional[Season] = None

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
            
            # Create player with random attributes
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
            await self.session.flush()  # Get team ID
            
            # Assign random number of players
            team_size = random.randint(
                TestDataConfig.MIN_PLAYERS_PER_TEAM,
                min(TestDataConfig.MAX_PLAYERS_PER_TEAM, len(available_players))
            )
            
            # First player becomes captain
            captain = available_players.pop()
            team_captain = TeamCaptain(
                team_id=team.id,
                player_uid=captain.uid
            )
            self.session.add(team_captain)
            
            # Add remaining players
            for _ in range(team_size - 1):
                if not available_players:
                    break
                player = available_players.pop()
                
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

    async def generate_tournament(self):
        """Generate a tournament within the current season"""
        if not self.season:
            raise ValueError("Season must be generated before tournament")
            
        logger.info("Generating tournament...")
        
        tournament = Tournament(
            season_id=self.season.id,
            name=f"{self.season.name} Regular Season",
            type=TournamentType.REGULAR,
            state=TournamentState.IN_PROGRESS,
            min_teams=2,
            max_teams=len(self.teams),
            max_team_size=TestDataConfig.MAX_PLAYERS_PER_TEAM,
            min_team_size=TestDataConfig.MIN_PLAYERS_PER_TEAM,
            registration_start=datetime.now() - timedelta(days=25),
            registration_end=datetime.now() - timedelta(days=20),
            scheduled_start_date=datetime.now() - timedelta(days=15),
            scheduled_end_date=datetime.now() + timedelta(days=15),
            format_config={
                "group_size": 4,
                "teams_per_group": len(self.teams) // 2,
                "teams_advancing": 4
            },
            map_pool=[str(map_obj.id) for map_obj in self.maps]
        )
        
        self.session.add(tournament)
        await self.session.commit()
        logger.info(f"Generated tournament: {tournament.name}")

    async def generate_matches(self, tournament_id: uuid.UUID):
        """Generate match history with realistic results"""
        logger.info("Generating matches...")
        
        # Create fixtures between teams
        for home_team in self.teams[:len(self.teams)//2]:
            for away_team in self.teams[len(self.teams)//2:]:
                fixture = Fixture(
                    tournament_id=tournament_id,
                    team_1=home_team.id,
                    team_2=away_team.id,
                    match_format="bo3",
                    scheduled_at=fake.date_time_between(
                        start_date='-14d',
                        end_date='+14d'
                    ),
                    status=FixtureStatus.COMPLETED
                )
                self.session.add(fixture)
                await self.session.flush()
                
                # Generate results for completed matches
                if fixture.scheduled_at < datetime.now():
                    # Random score favoring higher ELO team
                    team1_avg_elo = await self._get_team_average_elo(home_team.id)
                    team2_avg_elo = await self._get_team_average_elo(away_team.id)
                    
                    elo_diff = team1_avg_elo - team2_avg_elo
                    team1_win_prob = 1 / (1 + 10 ** (-elo_diff/400))
                    
                    # Generate map results
                    maps_played = random.randint(2, 3)
                    for map_num in range(maps_played):
                        team1_wins = random.random() < team1_win_prob
                        result = Result(
                            fixture_id=fixture.id,
                            map_id=random.choice(self.maps).id,
                            map_number=map_num + 1,
                            team_1_score=16 if team1_wins else random.randint(5, 14),
                            team_2_score=random.randint(5, 14) if team1_wins else 16,
                            team_1_side_first=random.choice(["CT", "T"]),
                            submitted_by=home_team.id,
                            confirmation_status=ConfirmationStatus.CONFIRMED
                        )
                        self.session.add(result)
        
        await self.session.commit()
        logger.info("Match generation completed")

    async def _get_team_average_elo(self, team_id: uuid.UUID) -> float:
        """Calculate average ELO for a team"""
        # This would need to be implemented based on your roster tracking
        # For now, return a random ELO within reasonable bounds
        return random.randint(TestDataConfig.MIN_ELO, TestDataConfig.MAX_ELO)

async def main():
    """Main function to generate test data"""
    from db.main import AsyncSession, engine
    
    async with AsyncSession(engine) as session:
        generator = TestDataGenerator(session)
        await generator.generate_all(
            num_players=50,
            num_teams=8,
            include_season=True
        )

if __name__ == "__main__":
    asyncio.run(main())