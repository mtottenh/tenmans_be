
from fastapi import Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from auth.dependencies import get_current_player
from auth.models import Player
from db.main import get_session

from services.season import season_service

async def get_active_season(
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    
    result = await season_service.get_active_season(session)
    return result