from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from typing import List, Optional
from competitions.models.seasons import Season, SeasonState
from ..schemas import SeasonCreate
import uuid

class SeasonStateError(Exception):
    pass

class SeasonService:
    async def create_season(
        self,
        season: SeasonCreate,
        session: AsyncSession
    ) -> Season:
        """Create a new season"""
        # Check if season with name exists
        existing = await self.get_season_by_name(season.name, session)
        if existing:
            raise ValueError(f"Season with name '{season.name}' already exists")
            
        new_season = Season(
            name=season.name,
            state=SeasonState.NOT_STARTED
        )
        session.add(new_season)
        await session.commit()
        await session.refresh(new_season)
        return new_season

    async def start_season(
        self,
        season_id: uuid.UUID,
        session: AsyncSession
    ) -> Season:
        """Start a season"""
        season = await self.get_season(season_id, session)
        if not season:
            raise ValueError("Season not found")
        
        if season.state != SeasonState.NOT_STARTED:
            raise SeasonStateError("Season can only be started from NOT_STARTED state")
            
        season.state = SeasonState.IN_PROGRESS
        session.add(season)
        await session.commit()
        await session.refresh(season)
        return season

    async def complete_season(
        self,
        season_id: uuid.UUID,
        session: AsyncSession
    ) -> Season:
        """Complete a season"""
        season = await self.get_season(season_id, session)
        if not season:
            raise ValueError("Season not found")
        
        if season.state != SeasonState.IN_PROGRESS:
            raise SeasonStateError("Can only complete an in-progress season")
            
        # Optionally: Add any completion validation logic here
            
        season.state = SeasonState.COMPLETED
        session.add(season)
        await session.commit()
        await session.refresh(season)
        return season

    async def reopen_season(
        self,
        season_id: uuid.UUID,
        session: AsyncSession
    ) -> Season:
        """Reopen a completed season"""
        season = await self.get_season(season_id, session)
        if not season:
            raise ValueError("Season not found")
        
        if season.state != SeasonState.COMPLETED:
            raise SeasonStateError("Can only reopen a completed season")
            
        season.state = SeasonState.IN_PROGRESS
        session.add(season)
        await session.commit()
        await session.refresh(season)
        return season

    async def get_season(
        self,
        season_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[Season]:
        """Get a season by ID"""
        stmt = select(Season).where(Season.id == season_id)
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_season_by_name(
        self,
        name: str,
        session: AsyncSession
    ) -> Optional[Season]:
        """Get a season by name"""
        stmt = select(Season).where(Season.name == name)
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_all_seasons(
        self,
        session: AsyncSession,
        include_completed: bool = True
    ) -> List[Season]:
        """Get all seasons"""
        stmt = select(Season)
        if not include_completed:
            stmt = stmt.where(Season.state != SeasonState.COMPLETED)
        stmt = stmt.order_by(desc(Season.created_at))
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_active_season(
        self,
        session: AsyncSession
    ) -> Optional[Season]:
        """Get the current active season"""
        stmt = select(Season).where(Season.state == SeasonState.IN_PROGRESS)
        result = (await session.execute(stmt)).scalars()
        return result.first()