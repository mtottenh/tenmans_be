from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from typing import List, Optional
from datetime import datetime
import uuid

from auth.models import Player, Role, VerificationStatus
from auth.schemas import PlayerVerificationUpdate, PlayerRoleAssign
from auth.service import AuthService, ScopeType
from moderation.models import Ban, BanStatus
from moderation.schemas import BanCreate
from audit.service import AuditService

class AdminServiceError(Exception):
    """Base exception for admin service errors"""
    pass

class AdminService:
    def __init__(self):
        self.auth_service = AuthService()
        self.audit_service = AuditService()

    def _player_audit_details(self, player: Player) -> dict:
        """Extract audit details for player operations"""
        return {
            "player_uid": str(player.uid),
            "player_name": player.name,
            "steam_id": player.steam_id,
            "verification_status": player.verification_status,
            "created_at": player.created_at.isoformat() if player.created_at else None,
            "updated_at": player.updated_at.isoformat() if player.updated_at else None
        }

    def _ban_audit_details(self, ban: Ban) -> dict:
        """Extract audit details for ban operations"""
        return {
            "ban_id": str(ban.id),
            "player_uid": str(ban.player_uid) if ban.player_uid else None,
            "team_id": str(ban.team_id) if ban.team_id else None,
            "scope": ban.scope,
            "reason": ban.reason,
            "status": ban.status,
            "start_date": ban.start_date.isoformat(),
            "end_date": ban.end_date.isoformat() if ban.end_date else None
        }

    @AuditService.audited_transaction(
        action_type="admin_get_players",
        entity_type="player"
    )
    async def get_all_players(
        self,
        skip: int,
        limit: int,
        actor: Player,
        session: AsyncSession
    ) -> List[Player]:
        """Get all players with pagination"""
        stmt = select(Player).offset(skip).limit(limit).order_by(desc(Player.created_at))
        result = (await session.execute(stmt)).scalars()
        return result.all()

    @AuditService.audited_transaction(
        action_type="admin_verify_player",
        entity_type="player",
        details_extractor=_player_audit_details
    )
    async def verify_player(
        self,
        player_uid: uuid.UUID,
        verification: PlayerVerificationUpdate,
        actor: Player,
        session: AsyncSession
    ) -> Player:
        """Process a player verification request"""
        player = await self.auth_service.get_player_by_uid(player_uid, session)
        if not player:
            raise AdminServiceError("Player not found")

        player.verification_status = verification.status
        player.verification_notes = verification.admin_notes
        player.verified_by = actor.uid
        player.verification_date =datetime.now(datetime.timezone.utc)
        player.updated_at = datetime.now(datetime.timezone.utc)

        session.add(player)
        return player

    @AuditService.audited_transaction(
        action_type="admin_ban_player",
        entity_type="player",
        details_extractor=_ban_audit_details
    )
    async def ban_player(
        self,
        player_uid: uuid.UUID,
        ban_data: BanCreate,
        actor: Player,
        session: AsyncSession
    ) -> Ban:
        """Create a new ban for a player"""
        player = await self.auth_service.get_player_by_uid(player_uid, session)
        if not player:
            raise AdminServiceError("Player not found")

        ban = Ban(
            player_uid=player.uid,
            scope=ban_data.scope,
            scope_id=ban_data.scope_id,
            reason=ban_data.reason,
            evidence=ban_data.evidence,
            status=BanStatus.ACTIVE,
            start_date=datetime.now(datetime.timezone.utc),
            end_date=ban_data.end_date,
            issued_by=actor.uid
        )

        session.add(ban)
        return ban

    @AuditService.audited_transaction(
        action_type="admin_revoke_ban",
        entity_type="ban",
        details_extractor=_ban_audit_details
    )
    async def revoke_ban(
        self,
        ban_id: uuid.UUID,
        reason: str,
        actor: Player,
        session: AsyncSession
    ) -> Ban:
        """Revoke an active ban"""
        ban = await session.get(Ban, ban_id)
        if not ban:
            raise AdminServiceError("Ban not found")

        if ban.status != BanStatus.ACTIVE:
            raise AdminServiceError("Ban is not active")

        ban.status = BanStatus.REVOKED
        ban.revoked_by = actor.uid
        ban.revoke_reason = reason

        session.add(ban)
        return ban

    async def get_player_bans(
        self,
        player_uid: uuid.UUID,
        include_inactive: bool,
        session: AsyncSession
    ) -> List[Ban]:
        """Get a player's ban history"""
        stmt = select(Ban).where(Ban.player_uid == player_uid)
        if not include_inactive:
            stmt = stmt.where(Ban.status == BanStatus.ACTIVE)
        stmt = stmt.order_by(desc(Ban.created_at))
        
        result = (await session.execute(stmt)).scalars()
        return result.all()

    @AuditService.audited_transaction(
        action_type="admin_assign_role",
        entity_type="player",
        details_extractor=_player_audit_details
    )
    async def assign_role(
        self,
        player_uid: uuid.UUID,
        role_data: PlayerRoleAssign,
        actor: Player,
        session: AsyncSession
    ) -> Player:
        """Assign a role to a player"""
        player = await self.auth_service.get_player_by_uid(player_uid, session)
        if not player:
            raise AdminServiceError("Player not found")

        role = await session.get(Role, role_data.role_id)
        if not role:
            raise AdminServiceError("Role not found")

        await self.auth_service.assign_role(
            player,
            role,
            ScopeType(role_data.scope_type),
            role_data.scope_id,
            session
        )

        return player