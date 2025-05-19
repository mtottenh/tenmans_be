import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.dependencies import (
    get_current_player,
    require_team_captain,
    require_tournament_manage,
    require_tournament_view,
)
from auth.models import Player
from competitions.map_pool.schemas import (
    MapPoolCreate,
    MapPoolResponse,
    MapPoolVoteRequest,
    MapPoolVoteResponse,
)
from competitions.tournament.service import TournamentServiceError
from db.main import get_session
from services.tournament import tournament_service


map_pool_router = APIRouter(prefix="/id/{tournament_id}/map-pool")


@map_pool_router.post(
    "/",
    response_model=MapPoolResponse,
    dependencies=[Depends(require_tournament_manage)],
)
async def create_map_pool(
    tournament_id: uuid.UUID,
    map_pool_data: MapPoolCreate,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Create map pool for tournament"""
    try:
        return await tournament_service.create_map_pool(
            tournament_id=tournament_id,
            map_pool_data=map_pool_data,
            actor=current_player,
            session=session,
        )
    except TournamentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@map_pool_router.get(
    "/", response_model=MapPoolResponse, dependencies=[Depends(require_tournament_view)]
)
async def get_map_pool(
    tournament_id: uuid.UUID,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Get map pool for tournament"""
    map_pool = await tournament_service.get_map_pool(tournament_id, session)
    if not map_pool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Map pool not found"
        )
    return map_pool


@map_pool_router.post(
    "/vote",
    response_model=MapPoolVoteResponse,
    dependencies=[Depends(require_team_captain)],
)
async def vote_for_maps(
    tournament_id: uuid.UUID,
    vote_request: MapPoolVoteRequest,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Vote for maps (team captain only)"""
    try:
        return await tournament_service.vote_for_maps(
            tournament_id=tournament_id,
            vote_request=vote_request,
            actor=current_player,
            session=session,
        )
    except TournamentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@map_pool_router.post(
    "/finalize",
    response_model=MapPoolResponse,
    dependencies=[Depends(require_tournament_manage)],
)
async def finalize_map_pool(
    tournament_id: uuid.UUID,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Finalize map pool"""
    try:
        return await tournament_service.finalize_map_pool(
            tournament_id=tournament_id, actor=current_player, session=session
        )
    except TournamentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
