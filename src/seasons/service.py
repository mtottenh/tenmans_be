from sqlmodel.ext.asyncio.session import AsyncSession

from src.fixtures.models import Fixture, Result, RoundType
from .schemas import SeasonCreateModel
from sqlmodel import select, desc
from .models import Season, SeasonState, Settings
from typing import List


class SeasonService:
    async def get_all_seasons(self, session: AsyncSession) -> List[Season]:
        stmnt = select(Season).order_by(desc(Season.created_at))
        result = await session.exec(stmnt)
        return result.all()

    async def create_new_season(self, season_data: SeasonCreateModel, session: AsyncSession) -> Season:
        season_data_dict = season_data.model_dump()
        new_season = Season(**season_data_dict)
        new_season.state = SeasonState.NOT_STARTED
        session.add(new_season)
        await session.commit()
        return new_season

    async def get_season(self, season_id: str, session: AsyncSession) -> Season | None:
        stmnt = select(Season).where(Season.id == season_id)
        result = await session.exec(stmnt)
        return result.first()
    
    async def get_season_by_name(self, name: str, session: AsyncSession) -> Season | None:
        stmnt = select(Season).where(Season.name == name)
        result = await session.exec(stmnt)
        return result.first()

    async def season_exists(self, name: str, session: AsyncSession) -> bool:
        season = await self.get_season_by_name(name, session)
        return season is not None
    
    async def set_active_season(self, season: Season, session: AsyncSession) -> Settings:
        stmnt = select(Settings).where(Settings.name == "active_season")
        result = await session.exec(stmnt)
        new_active_season_setting=Settings(name="active_season",value=season.name)
        current_season = result.first()
        if current_season:
            new_active_season_setting  = current_season
            new_active_season_setting.value = season.name
        session.add(new_active_season_setting)
        await session.commit()
        await session.refresh(new_active_season_setting)
        return new_active_season_setting

    async def get_active_season(self, session: AsyncSession) -> Season | None:
        stmnt = select(Settings).where(Settings.name == "active_season")
        result = await session.exec(stmnt)
        active_season_setting = result.first()
        if active_season_setting:
            stmnt = select(Season).where(Season.name == active_season_setting.value)
            result = await session.exec(stmnt)
            return result.first()
        return None
    
    async def group_stage_played_for_season(self, season: Season, session: AsyncSession):
        stmnt = select(Result.id).where(Result.fixture_id == Fixture.id, Fixture.season_id == season.id, Fixture.round.type == RoundType.GROUP_STAGE)
        all_results = (await session.exec(stmnt)).all()
        all_fixtures = (await session.exec(select(Fixture.id).where(Fixture.season_id == season.id, Fixture.round.type == RoundType.GROUP_STAGE))).all()
        return len(all_results) == len(all_fixtures)

        