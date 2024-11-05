from sqlmodel.ext.asyncio.session import AsyncSession
from .schemas import FixtureCreateModel, ResultCreateModel
from sqlmodel import select, desc, or_
from .models import Fixture, Result
from src.teams.models import Season, Team
from src.teams.service import TeamService, SeasonService
from enum import Enum, StrEnum
from datetime import datetime
from typing import List
import uuid

team_service = TeamService()
season_service = SeasonService()

class CreateFixtureError(StrEnum):
    TEAM_1_NO_EXIST = "Team 1 does not exist"
    TEAM_2_NO_EXIST = "Team 2 does not exist"
    INVALID_DATE = "Invalid scheduled_at date supplied"
    INVALID_SEASON = "Invalid season name"

class FixtureService:
    async def get_fixtures_for_season(self, season: Season, session: AsyncSession) -> List[Fixture]:
        stmnt = select(Fixture).where(Fixture.season_id == season.id).order_by(desc(Fixture.scheduled_at))
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
    
    async def add_result(self,  result: ResultCreateModel, session: AsyncSession) -> Result | None:
        stmnt = select(Fixture).where(Fixture.id == result.fixture_id)
        result = await session.exec(stmnt)
        if result.first() is None:
            return None
        result_obj=Result(**result.model_dump())
        session.add(result_obj)
        await session.commit()
        await session.refresh(result_obj)
        return result_obj