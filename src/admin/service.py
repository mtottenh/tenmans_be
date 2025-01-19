from datetime import datetime
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
import uuid
from sqlmodel import select, desc
from auth.models import Player, Role
from auth.schemas import PlayerStatus, PlayerVerificationUpdate, PlayerRoleAssign
from auth.service.auth import AuthService, create_auth_service
from moderation.models import Ban, BanStatus
from moderation.schemas import BanCreate

class AdminServiceError(Exception):
    """Base exception for admin service errors"""
    pass

class AdminService:
    def __init__(
        self,
        auth_service: AuthService,
    ):
        self.auth_service = auth_service

    async def verify_player(
        self,
        player_id: uuid.UUID,
        verification: PlayerVerificationUpdate,
        actor: Player,
        session: AsyncSession
    ) -> Player:
        """Process a player verification request"""
        player = await self.auth_service.get_player_by_id(player_id, session)
        if not player:
            raise AdminServiceError("Player not found")
        entity_metadata = {
                "verification_date": verification.verification_date.isoformat(),
                "verified_by": str(actor.id),
                "verification_notes": verification.admin_notes,

            }
        # Log the evidence used if submitted.
        if  player.verification_evidence is not None:
             entity_metadata["verification_evidence"] = player.verification_evidence
        await self.auth_service.change_player_status(
            player_id=player_id,
            new_status=verification.status,
            reason=verification.admin_notes,
            actor=actor,
            entity_metadata=entity_metadata,
            session=session
        )
        return player

    async def ban_player(
        self,
        player_id: uuid.UUID,
        ban_data: BanCreate,
        actor: Player,
        session: AsyncSession
    ) -> Ban:
        """Create a new ban for a player"""
        player = await self.auth_service.get_player_by_id(player_id, session)
        if not player:
            raise AdminServiceError("Player not found")

        # Create ban record first
        ban = Ban(
            player_id=player.id,
            scope=ban_data.scope,
            scope_id=ban_data.scope_id,
            reason=ban_data.reason,
            evidence=ban_data.evidence,
            status=BanStatus.ACTIVE,
            start_date=datetime.utcnow(),
            end_date=ban_data.end_date,
            issued_by=actor.id
        )
        session.add(ban)
        await session.flush()  # Get the ban ID

        # Use status transition service to update player status
        await self.auth_service.change_player_status(
            entity=player,
            new_status=PlayerStatus.BANNED,
            reason=ban_data.reason,
            actor=actor,
            entity_metadata={
                "ban_id": str(ban.id),
                "ban_scope": ban_data.scope,
                "ban_end_date": ban_data.end_date.isoformat() if ban_data.end_date else None
            },
            session=session
        )

        return ban
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

        # Update ban status
        ban.status = BanStatus.REVOKED
        ban.revoked_by = actor.id
        ban.revoke_reason = reason
        session.add(ban)
        await session.flush()

        # Check for other active bans
        active_bans = await self.get_player_bans(ban.player_id, False, session)
        if not active_bans:
            # Use status transition service to reactivate player
            player = await self.auth_service.get_player_by_id(ban.player_id, session)
            await self.auth_service.change_player_status(
                entity=player,
                new_status=PlayerStatus.ACTIVE,
                reason=f"Ban {ban_id} revoked: {reason}",
                actor=actor,
                entity_metadata={
                    "revoked_ban_id": str(ban.id)
                },
                session=session
            )

        return ban


    async def get_player_bans(
        self,
        player_id: uuid.UUID,
        include_inactive: bool,
        session: AsyncSession
    ) -> List[Ban]:
        """Get a player's ban history"""
        stmt = select(Ban).where(Ban.player_id == player_id)
        if not include_inactive:
            stmt = stmt.where(Ban.status == BanStatus.ACTIVE)
        stmt = stmt.order_by(desc(Ban.created_at))
        
        result = (await session.execute(stmt)).scalars()
        return result.all()


    async def assign_role(
        self,
        player_id: uuid.UUID,
        role_data: PlayerRoleAssign,
        actor: Player,
        session: AsyncSession
    ) -> Player:
        """Assign a role to a player"""
        player = await self.auth_service.get_player_by_id(player_id, session)
        if not player:
            raise AdminServiceError("Player not found")

        role = await session.get(Role, role_data.role_id)
        if not role:
            raise AdminServiceError("Role not found")

        # Use auth service to handle role assignment with proper scoping
        await self.auth_service.assign_role(
            player=player,
            role=role,
            scope_type=role_data.scope_type,
            scope_id=role_data.scope_id,
            actor=actor,
            session=session
        )

        return player


def create_admin_service() -> AdminService:
    """Create and configure AdminService with its dependencies"""
    auth_service = create_auth_service()
    
    return AdminService(
        auth_service=auth_service,
    )