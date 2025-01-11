from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
from datetime import datetime

from src.db.main import get_session
from src.auth.models import Player, Role, VerificationStatus, PlayerRole
from src.auth.schemas import (
    PlayerPrivate, 
    PlayerVerificationUpdate,
    PlayerRoleAssign,
    VerificationRequestResponse,
)
from src.auth.service import AuthService, PermissionScope, ScopeType
from src.auth.dependencies import (
    get_current_player,
    GlobalPermissionChecker,
    require_admin,
    require_moderator,
)
from src.audit.schemas import AuditLogCreate, AuditLogBase
from src.moderation.models import Ban, BanScope, BanStatus
from src.moderation.schemas import BanCreate, BanDetailed

admin_router = APIRouter(prefix="/admin/players")
auth_service = AuthService()

# Permission checkers
require_user_management = GlobalPermissionChecker(["manage_users"])
require_verification = GlobalPermissionChecker(["verify_users"])
require_ban_management = GlobalPermissionChecker(["manage_bans"])

@admin_router.get(
    "/", 
    response_model=List[PlayerPrivate],
    dependencies=[require_user_management]
)
async def get_all_players(
    session: AsyncSession = Depends(get_session),
    skip: int = 0,
    limit: int = 100
):
    """Get all players with full details (admin view)"""
    stmt = select(Player).offset(skip).limit(limit).order_by(desc(Player.created_at))
    players = await session.exec(stmt)
    return players.all()

@admin_router.get(
    "/verification-queue",
    response_model=List[VerificationRequestResponse],
    dependencies=[require_verification]
)
async def get_verification_requests(
    session: AsyncSession = Depends(get_session),
    status: Optional[VerificationStatus] = None,
    skip: int = 0,
    limit: int = 100
):
    """Get pending verification requests"""
    stmt = select(VerificationRequest)
    if status:
        stmt = stmt.where(VerificationRequest.status == status)
    stmt = stmt.offset(skip).limit(limit).order_by(desc(VerificationRequest.created_at))
    requests = await session.exec(stmt)
    return requests.all()

@admin_router.patch(
    "/{player_uid}/verify",
    response_model=PlayerPrivate,
    dependencies=[require_verification]
)
async def verify_player(
    player_uid: str,
    verification: PlayerVerificationUpdate,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Process a player verification request"""
    # Get player and their verification request
    player = await auth_service.get_player_by_uid(player_uid, session)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Update verification status
    player.verification_status = verification.status
    player.verification_notes = verification.admin_notes
    player.verified_by = current_admin.uid
    player.verification_date = datetime.utcnow()
    
    # Create audit log
    audit_log = AuditLogCreate(
        action_type="player_verification",
        entity_type="player",
        entity_id=player.uid,
        details={
            "status": verification.status,
            "admin_notes": verification.admin_notes,
            "admin_id": str(current_admin.uid)
        }
    )
    
    session.add(player)
    await session.commit()
    await session.refresh(player)
    
    return player

@admin_router.post(
    "/{player_uid}/ban",
    response_model=BanDetailed,
    dependencies=[require_ban_management]
)
async def ban_player(
    player_uid: str,
    ban_data: BanCreate,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Ban a player"""
    player = await auth_service.get_player_by_uid(player_uid, session)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Create ban record
    ban = Ban(
        player_uid=player.uid,
        scope=ban_data.scope,
        scope_id=ban_data.scope_id,
        reason=ban_data.reason,
        evidence=ban_data.evidence,
        status=BanStatus.ACTIVE,
        start_date=datetime.utcnow(),
        end_date=ban_data.end_date,
        issued_by=current_admin.uid
    )
    
    # Create audit log
    audit_log = AuditLogCreate(
        action_type="player_ban",
        entity_type="player",
        entity_id=player.uid,
        details={
            "ban_id": str(ban.id),
            "reason": ban_data.reason,
            "scope": ban_data.scope,
            "admin_id": str(current_admin.uid)
        }
    )
    
    session.add(ban)
    await session.commit()
    await session.refresh(ban)
    
    return ban

@admin_router.patch(
    "/bans/{ban_id}/revoke",
    response_model=BanDetailed,
    dependencies=[require_ban_management]
)
async def revoke_ban(
    ban_id: str,
    reason: str,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Revoke an active ban"""
    ban = await session.get(Ban, ban_id)
    if not ban:
        raise HTTPException(status_code=404, detail="Ban not found")
        
    if ban.status != BanStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Ban is not active")
    
    ban.status = BanStatus.REVOKED
    ban.revoked_by = current_admin.uid
    ban.revoke_reason = reason
    
    # Create audit log
    audit_log = AuditLogCreate(
        action_type="ban_revoke",
        entity_type="ban",
        entity_id=ban.id,
        details={
            "reason": reason,
            "admin_id": str(current_admin.uid)
        }
    )
    
    session.add(ban)
    await session.commit()
    await session.refresh(ban)
    
    return ban

@admin_router.get(
    "/{player_uid}/bans",
    response_model=List[BanDetailed],
    dependencies=[require_user_management]
)
async def get_player_bans(
    player_uid: str,
    session: AsyncSession = Depends(get_session),
    include_inactive: bool = False
):
    """Get a player's ban history"""
    stmt = select(Ban).where(Ban.player_uid == player_uid)
    if not include_inactive:
        stmt = stmt.where(Ban.status == BanStatus.ACTIVE)
    stmt = stmt.order_by(desc(Ban.created_at))
    
    bans = await session.exec(stmt)
    return bans.all()

@admin_router.patch(
    "/{player_uid}/roles",
    response_model=PlayerPrivate,
    dependencies=[require_admin]
)
async def assign_player_role(
    player_uid: str,
    role_data: PlayerRoleAssign,
    current_admin: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Assign a role to a player"""
    player = await auth_service.get_player_by_uid(player_uid, session)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    role = await session.get(Role, role_data.role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Create player role assignment
    player_role = await auth_service.assign_role(
        player,
        role,
        ScopeType(role_data.scope_type),
        role_data.scope_id,
        session
    )
    
    # Create audit log
    audit_log = AuditLogCreate(
        action_type="role_assignment",
        entity_type="player",
        entity_id=player.uid,
        details={
            "role_id": str(role.id),
            "role_name": role.name,
            "scope_type": role_data.scope_type,
            "scope_id": str(role_data.scope_id) if role_data.scope_id else None,
            "admin_id": str(current_admin.uid)
        }
    )
    
    await session.refresh(player)
    return player

@admin_router.get(
    "/{player_uid}/audit-log",
    response_model=List[AuditLogBase],
    dependencies=[require_user_management]
)
async def get_player_audit_log(
    player_uid: str,
    session: AsyncSession = Depends(get_session),
    skip: int = 0,
    limit: int = 100
):
    """Get audit log entries for a player"""
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity_type == "player")
        .where(AuditLog.entity_id == player_uid)
        .order_by(desc(AuditLog.created_at))
        .offset(skip)
        .limit(limit)
    )
    
    logs = await session.exec(stmt)
    return logs.all()
