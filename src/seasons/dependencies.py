
from fastapi import Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from src.players.dependencies import get_current_player
from src.players.models import Player
from src.db.main import get_session
from src.seasons.service import SeasonService

season_service = SeasonService()
async def get_active_season(
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    
    result = await season_service.get_active_season(session)
    return result