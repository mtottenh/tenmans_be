from sqlmodel.ext.asyncio.session import AsyncSession
from .schemas import FixtureCreateModel, ResultConfirmModel, ResultCreateModel
from sqlmodel import select, desc, or_
from .models import Fixture, Result, Round, RoundType
from src.teams.models import Team
from src.teams.service import TeamService, RosterService
from src.seasons.service import SeasonService
from src.seasons.models import Season
from enum import Enum, StrEnum
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

team_service = TeamService()
season_service = SeasonService()
roster_service = RosterService()

class FixtureGenerationError(Exception):
    pass

class CreateFixtureError(StrEnum):
    TEAM_1_NO_EXIST = "Team 1 does not exist"
    TEAM_2_NO_EXIST = "Team 2 does not exist"
    INVALID_DATE = "Invalid scheduled_at date supplied"
    INVALID_SEASON = "Invalid season name"

class FixtureService:
    async def get_fixtures_for_season(self, season: Season, session: AsyncSession) -> List[Fixture]:
        stmnt = select(Fixture, Round).where(Fixture.season_id == season.id).where(Fixture.round_id == Round.id).order_by(desc(Fixture.scheduled_at))
        result = await session.exec(stmnt)

        return result.all()
    
    async def get_fixtures_for_team_in_season(self, team: Team, season: Season, session: AsyncSession) -> List[Fixture]:
        stmnt = select(Fixture).where(Fixture.season_id == season.id).where(or_(Fixture.team_1 == team.id, Fixture.team_2 == team.id))
        result = await session.exec(stmnt)

        return result.all()
    
    async def get_fixture_by_id(self, fixture_id: str, session: AsyncSession) -> Fixture | None:
        stmnt = select(Fixture).where(Fixture.id == fixture_id)
        result = await session.exec(stmnt)

        return result.first()
    
    async def create_fixture_for_season(self, fixture_data: FixtureCreateModel, session: AsyncSession) -> CreateFixtureError | Fixture:
        scheduled_date = datetime.now()
        try:
            scheduled_date = datetime.strptime(fixture_data.scheduled_at, "%Y-%m-%d %H:%M")
        except ValueError as e:
            return CreateFixtureError.INVALID_DATE
        
        team_1 = await team_service.get_team_by_name(fixture_data.team_1, session)
        if team_1 is None:
            return CreateFixtureError.TEAM_1_NO_EXIST
        
        team_2 = await team_service.get_team_by_name(fixture_data.team_2, session)
        if team_2 is None:
            return CreateFixtureError.TEAM_2_NO_EXIST
        
        season = await season_service.get_season_by_name(fixture_data.season, session)
        if season is None:
            return CreateFixtureError.INVALID_SEASON
        
        fixture_data_dict = {}
        fixture_data_dict['team_1'] = team_1.id
        fixture_data_dict['team_2'] = team_2.id
        fixture_data_dict['season_id'] = season.id
        fixture_data_dict['scheduled_at'] = scheduled_date
        fixture_data_dict['round']
        new_fixture = Fixture(**fixture_data_dict)
        session.add(new_fixture)
        await session.commit()
        await session.refresh(new_fixture)
        return new_fixture

    async def update_fixture_date(self, fixture_id: str, new_date: datetime, session: AsyncSession):
        stmnt = select(Fixture).where(Fixture.id == fixture_id)
        fixture_o = await session.exec(stmnt)
        fixture = fixture_o.first()
        if fixture is not None:
            fixture.scheduled_at = new_date
            session.add(fixture)
            await session.commit()
            await session.refresh(fixture)
            return fixture
        else:
            return None


    async def create_round_robin_fixtures_with_rounds(self, season_id: uuid.UUID, session: AsyncSession):
        # Fetch all teams in the given season
        min_players=5
        teams = await roster_service.get_teams_with_min_players(season_id, min_players, session)
        team_ids = [team.id for team in teams]
        if len(team_ids) < 2:
            raise FixtureGenerationError("Less than 2 teams with active rosters of {min_players}")
        if len(team_ids) % 2 != 0:
            # If the number of teams is odd, add a 'bye' team (None) for round-robin balancing
            team_ids.append(None)
        
        num_teams = len(team_ids)
        rounds = num_teams - 1  # Total rounds needed for one complete round-robin
        
        # Scheduling parameters
        current_date = datetime.now()  # Start date for scheduling matches
        days_between_rounds = 7  # Days between each round

        # Generate fixtures by round
        for round_number in range(rounds):
            # Create a new round for the season
            round_instance = Round(
                season_id=season_id,
                type=RoundType.GROUP_STAGE,
                round_number=round_number + 1  # 1-based index for rounds
            )
            session.add(round_instance)
            await session.commit()  # Commit to assign an ID to the round
            await session.refresh(round_instance)
            # Generate fixtures for this round
            round_fixtures = []
            for i in range(num_teams // 2):
                team_1 = team_ids[i]
                team_2 = team_ids[num_teams - 1 - i]
                
                if team_1 is not None and team_2 is not None:
                    # Create fixtures with round_id association
                    fixture_home = Fixture(
                        team_1=team_1,
                        team_2=team_2,
                        season_id=season_id,
                        round_id=round_instance.id,
                        scheduled_at=current_date,
                    )
                    
                    fixture_away = Fixture(
                        team_1=team_2,
                        team_2=team_1,
                        season_id=season_id,
                        round_id=round_instance.id,
                        scheduled_at=current_date + timedelta(days=days_between_rounds * rounds)
                    )
                    
                    # Add fixtures to round's fixture list
                    round_fixtures.extend([fixture_home, fixture_away])
            
            # Rotate teams for the next round
            team_ids = [team_ids[0]] + [team_ids[-1]] + team_ids[1:-1]
            
            # Increment date for next round
            current_date += timedelta(days=days_between_rounds)
            
            # Add round fixtures to the session
            session.add_all(round_fixtures)
            await session.commit()

        print(f"Generated Group stage fixtures for season {season_id}, organized into {round_number + 1} rounds.")


    async def get_fixtures_for_season_and_round(self, season_id: uuid.UUID, round_number: int, session: AsyncSession) -> List[Fixture]:
        round_instance = (await session.exec(
            select(Round).where(Round.season_id == season_id, Round.round_number == round_number)
        )).first()

        if not round_instance:
            return []

        fixtures = (await session.exec(
            select(Fixture).where(Fixture.round_id == round_instance.id)
        )).all()

        return fixtures


    def determine_team_scores(self, results: List[Result]) -> List[tuple]:
        team_scores = {}

        for result in results:
            # Extract team IDs
            team_1 = result.fixture.team_1
            team_2 = result.fixture.team_2

            # Update scores (3 for a win, 1 for a draw)
            team_scores[team_1] = team_scores.get(team_1, 0)
            team_scores[team_2] = team_scores.get(team_2, 0)

            if result.score_team_1 > result.score_team_2:
                team_scores[team_1] += 3  # Win for team_1
            elif result.score_team_1 < result.score_team_2:
                team_scores[team_2] += 3  # Win for team_2
            else:
                team_scores[team_1] += 1  # Draw
                team_scores[team_2] += 1  # Draw

        # Create a sorted list of teams based on their scores
        sorted_teams = sorted(team_scores.items(), key=lambda item: item[1], reverse=True)
        return sorted_teams  # Returns a list of (team_id, score) tuples

    def determine_winners(self, fixtures: List[Fixture]) -> List[uuid.UUID]:
        winners = []

        for fixture in fixtures:
            # Assume results are set in the fixture
            if fixture.result and fixture.result.score_team_1 > fixture.result.score_team_2:
                winners.append(fixture.team_1)  # Team 1 wins
            elif fixture.result and fixture.result.score_team_1 < fixture.result.score_team_2:
                winners.append(fixture.team_2)  # Team 2 wins
            else:
                # In case of a draw or undefined results, handle accordingly
                # Here we can skip or handle further based on tournament rules
                raise ValueError("Results must be defined and cannot be a draw in knockout.")

        return winners

    async def generate_knockout_fixtures(self, winning_teams: List[uuid.UUID], season_id: uuid.UUID, round_number: int, session: AsyncSession) -> List[Fixture]:
        fixtures = []
        number_of_teams = len(winning_teams)

        # Check for odd number of teams to assign a bye if necessary
        has_bye = False
        if number_of_teams % 2 != 0:
            # Highest seed gets a bye
            bye_team = winning_teams[0]
            has_bye = True
            winning_teams = winning_teams[1:]  # Remove the bye team

        # Create the round in the database
        round_instance = Round(
            season_id=season_id,
            round_number=round_number,
            type=RoundType.KNOCKOUT
        )
        session.add(round_instance)
        await session.commit()  # Commit to get the round ID
        await session.refresh(round_instance)
        # Generate fixtures based on the winning teams
        for match_index in range(len(winning_teams) // 2):
            team_1 = winning_teams[match_index]                # Top-seeded team
            team_2 = winning_teams[-(match_index + 1)]        # Bottom-seeded team

            fixture = Fixture(
                team_1=team_1,
                team_2=team_2,
                season_id=season_id,
                round_id=round_instance.id,
                scheduled_at=datetime.now()  # Set fixture date/time as needed
            )
            fixtures.append(fixture)

        # If there was a bye, add a fixture for the bye team
        if has_bye:
            fixtures.append(Fixture(
                team_1=bye_team,
                team_2=None,  # Bye indicates no match
                season_id=season_id,
                round_id=round_instance.id,
                scheduled_at=datetime.now()
            ))

        return fixtures


    # Given the previous round number, schedule the next knockout round
    async def schedule_knockout_round(self, season_id: uuid.UUID, round_number: int, session: AsyncSession) -> List[Fixture]:
        # Fetch results from the previous round
        previous_round_fixtures = ( await 
            session.exec(
                select(Fixture).where(Fixture.round_id == round_number)
            )
        ).all()

        # Determine winning teams from the previous round
        winning_teams = self.determine_winners(previous_round_fixtures)
        if (len(winning_teams) == 1):
            return None
        # Generate fixtures for the current round
        return await self.generate_knockout_fixtures(winning_teams, season_id, round_number + 1, session)

    async def get_last_round(self, season_id: uuid.UUID, round_type: RoundType, session: AsyncSession) -> Optional[Round]:
        stmnt = select(Round.round_number).where(Round.season_id == season_id, Round.type == round_type).order_by(Round.round_number.desc())
        return (await session.exec(stmnt)).first()

    async def schedule_next_knockout_round(self, season_id, session: AsyncSession):
        last_round = await self.get_last_round(season_id, RoundType.KNOCKOUT, session)
        if last_round is None:
            raise FixtureGenerationError("Couldn't find any knockout rounds!")
        return await self.schedule_knockout_round(season_id, last_round.round_number + 1, session)


    async def initiate_knockout_tournament(self, season_id: uuid.UUID, session: AsyncSession):
        # Step 1: Fetch results of all fixtures from the group stage
        results = ( await session.exec(
            select(Result).join(Fixture)
            .where(Fixture.season_id == season_id)
        )).all()

        # Step 2: Determine all teams and their scores
        team_scores = self.determine_team_scores(results)
        # last_round = self.get_last_round(season_id, session)
        # if last_round is None:
        #     raise FixtureGenerationError(f"No rounds played in this season {season_id}")
        # Step 3: Generate fixtures for the knockout stage based on seeding
        knockout_fixtures = await self.generate_knockout_fixtures(team_scores, season_id, 1, session)

        # Step 4: Insert knockout fixtures into the database
        session.add_all(knockout_fixtures)
        await session.commit()

        print(f"Scheduled knockout fixtures for season {season_id}.")


class ResultsService:
    async def get_results_for_season(self, season: Season, session: AsyncSession) -> List[Result]:
        stmnt = select(Result, Fixture.id).where(Result.fixture_id == Fixture.id, Fixture.season_id == season.id)
        result = await session.exec(stmnt)
        return result.all()

    async def get_results_for_team_in_season(self,  team: Team, season: Season, session: AsyncSession) -> List[Result]:
        stmnt = select(Result, Fixture.id).where(Result.season_id == season.id, Result.fixture_id == Fixture.id).where(or_(Fixture.team_1 == team.id, Fixture.team_2 == team.id))
        result = await session.exec(stmnt)
        return result.all()
    
    async def get_result_for_fixture(self, fixture_id: str, session: AsyncSession):
        stmnt = select(Result).where(Result.fixture_id == fixture_id)
        result = await session.exec(stmnt)
        return result.first()
    
    async def add_result(self,  result: ResultCreateModel, submitted_by, session: AsyncSession, confirmed=False) -> Result:
        stmnt = select(Result).where(Fixture.id == result.fixture_id).where(Fixture.id == Result.fixture_id)
        result_obj = await session.exec(stmnt)
        r = result_obj.first()
        if r is not None:
            return None
        r = Result(**result.model_dump())
        r.score_team_1 = result.score_team_1
        r.score_team_2 = result.score_team_2
        r.submitted_by = submitted_by
        r.confirmed = confirmed
        session.add(r)
        await session.commit()
        await session.refresh(r)
        return r
    
    async def confirm_result(self, result:  ResultConfirmModel, session:AsyncSession) -> Result:
        stmnt = select(Result).where(Fixture.id == result.fixture_id).where(Fixture.id == Result.fixture_id)
        result_obj = await session.exec(stmnt)
        r: Optional[Result] = result_obj.first()
        if r is None:
            return None
        r.confirmed = True
        session.add(r)
        await session.commit()
        await session.refresh(r)
        return r