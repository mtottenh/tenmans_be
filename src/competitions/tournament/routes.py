from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
import uuid

from db.main import get_session
from auth.models import Player
from auth.dependencies import (
    get_current_player,
    GlobalPermissionChecker,
    TournamentPermissionChecker
)
from .service import TournamentService, TournamentServiceError
from .schemas import (
    RegistrationReviewRequest,
    RegistrationStatus,
    RegistrationWithdrawRequest,
    TournamentCreate,
    TournamentRegistrationBase,
    TournamentRegistrationDetail,
    TournamentRegistrationList,
    TournamentRegistrationRequest,
    TournamentUpdate,
    TournamentBase,
    TournamentWithStats,
    TournamentStandings
)

tournament_router = APIRouter(prefix="/tournaments")
tournament_service = TournamentService()

# Permission checkers
require_tournament_admin = GlobalPermissionChecker(["manage_tournaments"])
require_tournament_manage = TournamentPermissionChecker(["manage_tournament"])
require_tournament_view = TournamentPermissionChecker(["view_tournament"])

@tournament_router.get(
    "/",
    response_model=List[TournamentBase],
    dependencies=[Depends(require_tournament_view)]
)
async def get_all_tournaments(
    season_id: uuid.UUID,
    include_completed: bool = True,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get all tournaments for a season"""
    return await tournament_service.get_tournaments_by_season(
        season_id,
        session,
        include_completed
    )

@tournament_router.post(
    "/",
    response_model=TournamentBase,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tournament_admin)]
)
async def create_tournament(
    tournament_data: TournamentCreate,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Create a new tournament"""
    try:
        return await tournament_service.create_tournament(
            tournament_data,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.get(
    "/{tournament_id}",
    response_model=TournamentWithStats,
    dependencies=[Depends(require_tournament_view)]
)
async def get_tournament(
    tournament_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get tournament details with stats"""
    tournament = await tournament_service.get_tournament(tournament_id, session)
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    return tournament

@tournament_router.patch(
    "/{tournament_id}",
    response_model=TournamentBase,
    dependencies=[Depends(require_tournament_manage)]
)
async def update_tournament(
    tournament_id: uuid.UUID,
    update_data: TournamentUpdate,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Update tournament details"""
    try:
        tournament = await tournament_service.get_tournament(tournament_id, session)
        if not tournament:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tournament not found"
            )

        return await tournament_service.update_tournament(
            tournament,
            update_data,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.post(
    "/{tournament_id}/start",
    response_model=TournamentBase,
    dependencies=[Depends(require_tournament_manage)]
)
async def start_tournament(
    tournament_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Start a tournament"""
    try:
        tournament = await tournament_service.get_tournament(tournament_id, session)
        if not tournament:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tournament not found"
            )

        return await tournament_service.start_tournament(
            tournament,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.post(
    "/{tournament_id}/complete",
    response_model=TournamentBase,
    dependencies=[Depends(require_tournament_manage)]
)
async def complete_tournament(
    tournament_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Complete a tournament"""
    try:
        tournament = await tournament_service.get_tournament(tournament_id, session)
        if not tournament:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tournament not found"
            )

        return await tournament_service.complete_tournament(
            tournament,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.post(
    "/{tournament_id}/cancel",
    response_model=TournamentBase,
    dependencies=[Depends(require_tournament_manage)]
)
async def cancel_tournament(
    tournament_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Cancel a tournament"""
    try:
        tournament = await tournament_service.get_tournament(tournament_id, session)
        if not tournament:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tournament not found"
            )

        return await tournament_service.cancel_tournament(
            tournament,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.get(
    "/{tournament_id}/standings",
    response_model=TournamentStandings,
    dependencies=[Depends(require_tournament_view)]
)
async def get_tournament_standings(
    tournament_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get current tournament standings"""
    try:
        return await tournament_service.get_tournament_standings(tournament_id, session)
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Registration endpoints
@tournament_router.post(
    "/{tournament_id}/registrations",
    response_model=TournamentRegistrationBase,
    dependencies=[Depends(require_tournament_view)]  # Basic tournament view permission needed
)
async def request_tournament_registration(
    tournament_id: uuid.UUID,
    registration: TournamentRegistrationRequest,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Request registration for a tournament"""
    try:
        return await tournament_service.request_registration(
            tournament_id,
            registration,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.get(
    "/{tournament_id}/registrations",
    response_model=TournamentRegistrationList,
    dependencies=[Depends(require_tournament_view)]
)
async def get_tournament_registrations(
    tournament_id: uuid.UUID,
    status: Optional[RegistrationStatus] = None,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get all registrations for a tournament, optionally filtered by status"""
    return await tournament_service.get_registrations(
        tournament_id,
        status,
        session
    )

@tournament_router.get(
    "/{tournament_id}/registrations/{registration_id}",
    response_model=TournamentRegistrationDetail,
    dependencies=[Depends(require_tournament_view)]
)
async def get_tournament_registration(
    tournament_id: uuid.UUID,
    registration_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get details of a specific tournament registration"""
    registration = await tournament_service.get_registration(
        tournament_id,
        registration_id,
        session
    )
    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration not found"
        )
    return registration

@tournament_router.post(
    "/{tournament_id}/registrations/{registration_id}/review",
    response_model=TournamentRegistrationDetail,
    dependencies=[Depends(require_tournament_manage)]
)
async def review_tournament_registration(
    tournament_id: uuid.UUID,
    registration_id: uuid.UUID,
    review: RegistrationReviewRequest,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Review (approve/reject) a tournament registration"""
    try:
        return await tournament_service.review_registration(
            tournament_id,
            registration_id,
            review,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.post(
    "/{tournament_id}/registrations/{registration_id}/withdraw",
    response_model=TournamentRegistrationDetail,
    dependencies=[Depends(require_tournament_view)]  # Will check team captain status in service
)
async def withdraw_from_tournament(
    tournament_id: uuid.UUID,
    registration_id: uuid.UUID,
    withdrawal: RegistrationWithdrawRequest,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Withdraw a team from a tournament"""
    try:
        return await tournament_service.withdraw_registration(
            tournament_id,
            registration_id,
            withdrawal,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
# Permission checkers
require_tournament_manage = GlobalPermissionChecker(["manage_tournaments"])
require_tournament_view = GlobalPermissionChecker(["view_tournaments"])

# Tournament Management Routes
@tournament_router.post(
    "/{tournament_id}/generate",
    response_model=TournamentWithStats,
    dependencies=[Depends(require_tournament_manage)]
)
async def generate_tournament_structure(
    tournament_id: uuid.UUID,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Generate tournament structure including rounds and fixtures"""
    try:
        tournament = await tournament_service.generate_tournament_structure(
            tournament_id,
            current_player,
            session
        )
        
        # Add extended stats to response
        return await tournament_service.get_tournament_with_stats(tournament.id, session)
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.post(
    "/{tournament_id}/start",
    response_model=TournamentBase,
    dependencies=[Depends(require_tournament_manage)]
)
async def start_tournament(
    tournament_id: uuid.UUID,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Start a tournament"""
    try:
        return await tournament_service.start_tournament(
            tournament_id,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.post(
    "/{tournament_id}/rounds/{round_number}/complete",
    response_model=TournamentBase,
    dependencies=[Depends(require_tournament_manage)]
)
async def complete_tournament_round(
    tournament_id: uuid.UUID,
    round_number: int,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Complete a tournament round and progress to next"""
    try:
        return await tournament_service.complete_round(
            tournament_id,
            round_number,
            current_player,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@tournament_router.get(
    "/{tournament_id}/standings",
    response_model=TournamentStandings,
    dependencies=[Depends(require_tournament_view)]
)
async def get_tournament_standings(
    tournament_id: uuid.UUID,
    session: AsyncSession = Depends(get_session)
):
    """Get current tournament standings"""
    try:
        return await tournament_service.get_tournament_standings(
            tournament_id,
            session
        )
    except TournamentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
