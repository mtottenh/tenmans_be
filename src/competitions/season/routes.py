from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
import uuid

from db.main import get_session
from auth.dependencies import get_current_player, GlobalPermissionChecker
from auth.models import Player
from ..models.seasons import Season
from .service import SeasonService, SeasonStateError

season_router = APIRouter(prefix="/seasons")
season_service = SeasonService()

# Permission checker
require_season_admin = GlobalPermissionChecker(["manage_seasons"])

@season_router.post("/", response_model=Season, status_code=status.HTTP_201_CREATED)
async def create_season(
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
    current_user: Player = Depends(get_current_player),
    _: bool = Depends(require_season_admin)
):
    """Create a new season"""
    try:
        return await season_service.create_season(name, session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@season_router.get("/", response_model=List[Season])
async def get_all_seasons(
    include_completed: bool = True,
    session: AsyncSession = Depends(get_session),
    current_user: Player = Depends(get_current_player)
):
    """Get all seasons"""
    return await season_service.get_all_seasons(session, include_completed)

@season_router.get("/active", response_model=Optional[Season])
async def get_active_season(
    session: AsyncSession = Depends(get_session),
    current_user: Player = Depends(get_current_player)
):
    """Get current active season"""
    return await season_service.get_active_season(session)

@season_router.get("/{season_id}", response_model=Season)
async def get_season(
    season_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: Player = Depends(get_current_player)
):
    """Get a specific season"""
    season = await season_service.get_season(season_id, session)
    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Season not found"
        )
    return season

@season_router.post("/{season_id}/start", response_model=Season)
async def start_season(
    season_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: Player = Depends(get_current_player),
    _: bool = Depends(require_season_admin)
):
    """Start a season"""
    try:
        return await season_service.start_season(season_id, session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except SeasonStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@season_router.post("/{season_id}/complete", response_model=Season)
async def complete_season(
    season_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: Player = Depends(get_current_player),
    _: bool = Depends(require_season_admin)
):
    """Complete a season"""
    try:
        return await season_service.complete_season(season_id, session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except SeasonStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@season_router.post("/{season_id}/reopen", response_model=Season)
async def reopen_season(
    season_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: Player = Depends(get_current_player),
    _: bool = Depends(require_season_admin)
):
    """Reopen a completed season"""
    try:
        return await season_service.reopen_season(season_id, session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except SeasonStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )