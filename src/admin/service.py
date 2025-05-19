import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from audit.schemas import AuditEventType
from audit.service import AuditService
from auth.models import Player, Role
from auth.schemas import PlayerRoleAssign, PlayerStatus, PlayerVerificationUpdate
from auth.service.auth import AuthService, create_auth_service
from moderation.models import Ban, BanStatus
from moderation.schemas import BanCreate
from status.service import StatusTransitionService, create_status_transition_service


class AdminServiceError(Exception):
    """Base exception for admin service errors"""

    pass


class AdminService:
    def __init__(
        self,
        auth_service: AuthService,
        status_service: StatusTransitionService,
    ):
        self.auth_service = auth_service
        self.status_transition_service = status_service

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Player"
    )
    async def verify_player(
        self,
        player_id: uuid.UUID,
        verification: PlayerVerificationUpdate,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> Player:
        """Process a player verification request"""
        player = await session.get(Player, player_id)
        if not player:
            raise ValueError("Player not found")

        entity_metadata = {
            "verification_date": verification.verification_date.isoformat(),
            "verified_by": str(actor.id),
            "verification_notes": verification.admin_notes,
        }

        # Log the evidence used if submitted
        if player.verification_evidence:
            entity_metadata["verification_evidence"] = player.verification_evidence

        # Use status transition service to trigger appropriate pipeline
        await self.status_transition_service.transition_status(
            entity=player,
            new_status=verification.status,
            reason=verification.admin_notes,
            actor=actor,
            entity_metadata=entity_metadata,
            session=session,
            audit_context=audit_context,
        )

        return player

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE, entity_type="Ban"
    )
    async def ban_player(
        self,
        player_id: uuid.UUID,
        ban_data: BanCreate,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> Ban:
        """Ban a player and trigger the ban pipeline"""
        player = await session.get(Player, player_id)
        if not player:
            raise ValueError("Player not found")

        # Create ban record first
        ban = Ban(
            player_id=player.id,
            scope=ban_data.scope,
            scope_id=ban_data.scope_id,
            reason=ban_data.reason,
            evidence=ban_data.evidence,
            status=BanStatus.ACTIVE,
            start_date=datetime.now(timezone.utc),
            end_date=ban_data.end_date,
            issued_by=actor.id,
        )
        session.add(ban)
        await session.flush()  # Get the ban ID

        # Prepare additional context for pipeline
        ban_context = {
            "ban_id": str(ban.id),
            "ban_scope": ban_data.scope,
            "ban_end_date": ban_data.end_date.isoformat()
            if ban_data.end_date
            else None,
            "role_service": self.role_service,  # Pass role service for potential use in pipeline steps
        }

        # Use status transition service to trigger ban pipeline
        await self.status_transition_service.transition_status(
            entity=player,
            new_status=PlayerStatus.BANNED,
            reason=ban_data.reason,
            actor=actor,
            entity_metadata=ban_context,
            session=session,
            audit_context=audit_context,
        )

        return ban

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Ban"
    )
    async def revoke_ban(
        self,
        ban_id: uuid.UUID,
        reason: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> Ban:
        """Revoke a ban and restore player status"""
        ban = await session.get(Ban, ban_id)
        if not ban:
            raise ValueError("Ban not found")

        if ban.status != BanStatus.ACTIVE:
            raise ValueError("Ban is not active")

        # Update ban status
        ban.status = BanStatus.REVOKED
        ban.revoked_by = actor.id
        ban.revoke_reason = reason
        session.add(ban)
        await session.flush()

        # Check if there are any other active bans
        stmt = select(Ban).where(
            Ban.player_id == ban.player_id, Ban.status == BanStatus.ACTIVE
        )
        active_bans = (await session.execute(stmt)).scalars().all()

        # If no other active bans, restore player
        if not active_bans:
            player = await session.get(Player, ban.player_id)
            if player and player.status == PlayerStatus.BANNED:
                # Prepare context for pipeline
                unban_context = {
                    "revoked_ban_id": str(ban.id),
                    "revoke_reason": reason,
                    "auth_service": self.auth_service,
                }

                # Use status transition service to trigger unban pipeline
                await self.status_transition_service.transition_status(
                    entity=player,
                    new_status=PlayerStatus.ACTIVE,
                    reason=f"Ban {ban_id} revoked: {reason}",
                    actor=actor,
                    entity_metadata=unban_context,
                    session=session,
                    audit_context=audit_context,
                )

        return ban

    async def get_player_bans(
        self, player_id: uuid.UUID, include_inactive: bool, session: AsyncSession
    ) -> list[Ban]:
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
        session: AsyncSession,
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
            session=session,
        )

        return player


def create_admin_service(
    auth_svc: Optional[AuthService] = None,
    status_transition_svc: Optional[StatusTransitionService] = None,
) -> AdminService:
    """Create and configure AdminService with its dependencies"""
    auth_service = auth_svc or create_auth_service()
    status_transition_service = (
        status_transition_svc or create_status_transition_service()
    )
    return AdminService(
        auth_service=auth_service,
        status_service=status_transition_service,
    )
