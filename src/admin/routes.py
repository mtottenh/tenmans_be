from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
from datetime import datetime

from src.db.main import get_session
from src.auth.models import Player
from src.auth.schemas import (
    PlayerPrivate,
    PlayerVerificationUpdate,
    PlayerRoleAssign,
    VerificationRequestResponse
)
from src.auth.dependencies import (
    get_current_player,
    GlobalPermissionChecker,
)
from src.moderation.schemas import BanCreate, BanDetailed
from src.audit.schemas import AuditLogBase
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