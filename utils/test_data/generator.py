"""Test data generation utilities for CS2 10mans system."""

import random
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import asyncio
import logging
from faker import Faker
import sys
import os


sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src'))

from sqlmodel.ext.asyncio.session import AsyncSession
from auth.schemas import PlayerStatus

from auth.models import Player, AuthType
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
    MIN_ELO = 2000
    MAX_ELO = 30000
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
        if include_season:
            await self.generate_season()
        # await self.generate_maps()
        await self.generate_players(num_players)
        await self.generate_teams(num_teams)
        if include_season:    
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
                status=random.choice(list(PlayerStatus)),
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
        async with self.session.begin():
            for i in range(count):
                # Create team
                team = Team(
                    name=f"Team {fake.unique.word().title()}",
                    created_at=fake.date_time_between(
                        start_date='-6m',
                        end_date='now'
                    )
                )
                
                self.session.add(team)  # Add team to the session
                logger.info("Before session.flush()")
                await self.session.flush()  # Flush to get the team's ID
                logger.info("After session.flush()")
                await self.session.refresh(team)
                team_id = team.id  # Get the assigned team ID

                # Assign a captain
                
                captain = available_players.pop()
                await self.session.refresh(captain)
                team_captain = TeamCaptain(
                    team_id=team_id,
                    player_id=captain.id
                )
                self.session.add(team_captain)

                # Add remaining players to the roster
                team_size = random.randint(
                    TestDataConfig.MIN_PLAYERS_PER_TEAM,
                    min(TestDataConfig.MAX_PLAYERS_PER_TEAM, len(available_players))
                )
                logger.info("Adding players to the team roster")
                for _ in range(team_size - 1):
                    if not available_players:
                        break
                    player = available_players.pop()
                    await self.session.refresh(player)
                    season  = self.season
                    await self.session.refresh(season)
                    roster_entry = Roster(
                        season_id=season.id,
                        team_id=team_id,  # Link the player to the team
                        player_id=player.id  # Ensure correct player association
                    )
                    logger.info(f"Creating roster entry for {player.name}")
                    self.session.add(roster_entry)
                
                self.teams.append(team)  # Track team in the list
            
            await self.session.commit()  # Commit the team and its relationships
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
        await self.session.refresh(self.season)
        logger.info(f"Generated season: {self.season.name}")

    async def generate_tournament(self):
        """Generate a tournament within the current season"""
        if not self.season:
            raise ValueError("Season must be generated before tournament")
            
        logger.info("Generating tournament...")
        await self.session.refresh(self.season)
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
                "teams_per_group": len(self.teams) // 2,
                "match_format": "bo3"
            },
            map_pool=[str(map_obj.id) for map_obj in self.maps]
        )
        
        self.session.add(tournament)
        await self.session.commit()
        await self.session.refresh(tournament)
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
                await self.session.refresh(fixture)
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