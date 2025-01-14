import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
from datetime import datetime

from admin.schemas import ExtendRoundRequest, RoundForfeitRequest, UndoForfeitRequest
from competitions.models.fixtures import Fixture
from competitions.models.rounds import Round
from competitions.rounds.service import RoundService, RoundServiceError
from competitions.tournament.service import TournamentService
from db.main import get_session
from auth.models import Player
from auth.schemas import (
    PlayerPrivate,
    PlayerVerificationUpdate,
    PlayerRoleAssign,
    VerificationRequestResponse
)
from auth.dependencies import (
    get_current_player,
    GlobalPermissionChecker,
)
from moderation.schemas import BanCreate, BanDetailed
from audit.schemas import AuditLogBase
from .service import AdminService, AdminServiceError

admin_router = APIRouter(prefix="/admin/players")
admin_service = AdminService()

# Permission checkers
require_user_management = GlobalPermissionChecker(["manage_users"])
require_verification = GlobalPermissionChecker(["verify_users"])
require_ban_management = GlobalPermissionChecker(["manage_bans"])
require_role_management = GlobalPermissionChecker(["manage_roles"])

@admin_router.get(
    "/",
    response_model=List[PlayerPrivate],
    dependencies=[Depends(require_user_management)]
)
async def get_all_players(
    skip: int = 0,
    limit: int = 100,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Get all players with full details (admin view)"""
    try:
        return await admin_service.get_all_players(
            skip=skip,
            limit=limit,
            actor=current_admin,
            session=session
        )
    except AdminServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@admin_router.patch(
    "/{player_uid}/verify",
    response_model=PlayerPrivate,
    dependencies=[Depends(require_verification)]
)
async def verify_player(
    player_uid: str,
    verification: PlayerVerificationUpdate,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Process a player verification request"""
    try:
        return await admin_service.verify_player(
            player_uid=player_uid,
            verification=verification,
            actor=current_admin,
            session=session
        )
    except AdminServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@admin_router.post(
    "/{player_uid}/ban",
    response_model=BanDetailed,
    dependencies=[Depends(require_ban_management)]
)
async def ban_player(
    player_uid: str,
    ban_data: BanCreate,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Ban a player"""
    try:
        return await admin_service.ban_player(
            player_uid=player_uid,
            ban_data=ban_data,
            actor=current_admin,
            session=session
        )
    except AdminServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@admin_router.patch(
    "/bans/{ban_id}/revoke",
    response_model=BanDetailed,
    dependencies=[Depends(require_ban_management)]
)
async def revoke_ban(
    ban_id: str,
    reason: str,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Revoke an active ban"""
    try:
        return await admin_service.revoke_ban(
            ban_id=ban_id,
            reason=reason,
            actor=current_admin,
            session=session
        )
    except AdminServiceError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@admin_router.get(
    "/{player_uid}/bans",
    response_model=List[BanDetailed],
    dependencies=[Depends(require_user_management)]
)
async def get_player_bans(
    player_uid: str,
    session: AsyncSession = Depends(get_session),
    include_inactive: bool = False
):
    """Get a player's ban history"""
    try:
        return await admin_service.get_player_bans(
            player_uid=player_uid,
            include_inactive=include_inactive,
            session=session
        )
    except AdminServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@admin_router.patch(
    "/{player_uid}/roles",
    response_model=PlayerPrivate,
    dependencies=[Depends(require_role_management)]
)
async def assign_player_role(
    player_uid: str,
    role_data: PlayerRoleAssign,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Assign a role to a player"""
    try:
        return await admin_service.assign_role(
            player_uid=player_uid,
            role_data=role_data,
            actor=current_admin,
            session=session
        )
    except AdminServiceError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    


tournament_service = TournamentService()
round_manager = RoundService()

# Permission checker
require_tournament_admin = GlobalPermissionChecker(["tournament_admin"])

@admin_router.patch(
    "/{tournament_id}/rounds/{round_number}/extend",
    response_model=Round,
    dependencies=[Depends(require_tournament_admin)]
)
async def extend_round_deadline(
    tournament_id: uuid.UUID,
    round_number: int,
    extension: ExtendRoundRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Extend a round's deadline"""
    try:
        # Get the round
        round = await tournament_service._get_round_by_number(
            tournament_id, 
            round_number, 
            session
        )
        if not round:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )

        return await round_manager.extend_round_deadline(
            round=round,
            new_end_date=extension.new_end_date,
            reason=extension.reason,
            actor=current_admin,
            session=session
        )
    except RoundServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@admin_router.post(
    "/{tournament_id}/rounds/{round_number}/forfeit-unplayed",
    response_model=List[Fixture],
    dependencies=[Depends(require_tournament_admin)]
)
async def forfeit_unplayed_matches(
    tournament_id: uuid.UUID,
    round_number: int,
    forfeit_data: RoundForfeitRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Forfeit all unplayed matches in a round"""
    try:
        round = await tournament_service._get_round_by_number(
            tournament_id, 
            round_number, 
            session
        )
        if not round:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )

        return await round_manager.forfeit_unplayed_fixtures(
            round=round,
            forfeit_notes=forfeit_data.forfeit_notes,
            actor=current_admin,
            session=session
        )
    except RoundServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@admin_router.post(
    "/{tournament_id}/rounds/{round_number}/reopen",
    response_model=Round,
    dependencies=[Depends(require_tournament_admin)]
)
async def reopen_round(
    tournament_id: uuid.UUID,
    round_number: int,
    extension: ExtendRoundRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Reopen a completed round"""
    try:
        round = await tournament_service._get_round_by_number(
            tournament_id, 
            round_number, 
            session
        )
        if not round:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )

        return await round_manager.reopen_round(
            round=round,
            new_end_date=extension.new_end_date,
            reason=extension.reason,
            actor=current_admin,
            session=session
        )
    except RoundServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@admin_router.post(
    "/{tournament_id}/fixtures/{fixture_id}/undo-forfeit",
    response_model=Fixture,
    dependencies=[Depends(require_tournament_admin)]
)
async def undo_fixture_forfeit(
    tournament_id: uuid.UUID,
    fixture_id: uuid.UUID,
    undo_data: UndoForfeitRequest,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Undo a fixture forfeit"""
    try:
        fixture = await tournament_service._get_fixture(fixture_id, session)
        if not fixture or fixture.tournament_id != tournament_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fixture not found"
            )

        return await round_manager.undo_fixture_forfeit(
            fixture=fixture,
            reason=undo_data.reason,
            actor=current_admin,
            session=session
        )
    except RoundServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
# Extend round request
# forefit request
# undo forefit request    