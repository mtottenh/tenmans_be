import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player, PlayerRole
from auth.schemas import PlayerStatus, ScopeType
from competitions.models.fixtures import Fixture, FixtureStatus
from status.pipeline import TransitionStep
from teams.base_schemas import RosterStatus, TeamCaptainStatus
from teams.models import Roster, TeamCaptain


LOG = logging.getLogger("uvicorn.error")


class PlayerRosterDeactivateStep(TransitionStep):
    """Pipeline step to update all active roster entries when a player is banned"""

    async def execute(
        self,
        entity: Player,
        old_status: str,  # noqa: ARG002
        new_status: str,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
        **context,
    ) -> None:
        if new_status != PlayerStatus.BANNED.value:
            return  # Only act on ban transitions

        # Get all active roster entries for this player
        stmt = select(Roster).where(
            Roster.player_id == entity.id, Roster.status == RosterStatus.ACTIVE
        )
        result = await session.execute(stmt)
        rosters = result.scalars().all()

        # Update roster status to REMOVED
        for roster in rosters:
            LOG.info(
                f"Setting roster entry for team {roster.team_id} to REMOVED due to player ban"
            )
            roster.status = RosterStatus.REMOVED
            roster.updated_at = datetime.now(timezone.utc)
            session.add(roster)


class PlayerCaptainDeactivateStep(TransitionStep):
    """Pipeline step to remove captain roles when a player is banned"""

    async def execute(
        self,
        entity: Player,
        old_status: str,  # noqa: ARG002
        new_status: str,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
        **context,
    ) -> None:
        if new_status != PlayerStatus.BANNED.value:
            return  # Only act on ban transitions

        # Get all active captain entries for this player
        stmt = select(TeamCaptain).where(
            TeamCaptain.player_id == entity.id,
            TeamCaptain.status.in_(
                [TeamCaptainStatus.ACTIVE, TeamCaptainStatus.TEMPORARY]
            ),
        )
        result = await session.execute(stmt)
        captains = result.scalars().all()

        # Update captain status to DISBANDED
        for captain in captains:
            LOG.info(
                f"Setting captain entry for team {captain.team_id} to REMOVED due to player ban"
            )
            captain.status = TeamCaptainStatus.REMOVED
            session.add(captain)


class PlayerFixtureSubstituteStep(TransitionStep):
    """Pipeline step to replace player in upcoming fixtures when banned"""

    async def execute(
        self,
        entity: Player,
        old_status: str,  # noqa: ARG002
        new_status: str,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
        **context,
    ) -> None:
        if new_status != PlayerStatus.BANNED.value:
            return  # Only act on ban transitions

        from matches.models import MatchPlayer

        # Get all upcoming match participations
        stmt = (
            select(MatchPlayer)
            .join(Fixture, MatchPlayer.fixture_id == Fixture.id)
            .where(
                MatchPlayer.player_id == entity.id,
                Fixture.status == FixtureStatus.SCHEDULED,
            )
        )
        result = await session.execute(stmt)
        match_players = result.scalars().all()

        # Remove player from upcoming matches
        # In a real implementation, this might try to find substitutes
        for match_player in match_players:
            LOG.info(
                f"Removing player from fixture {match_player.fixture_id} due to ban"
            )
            await session.delete(match_player)


class PlayerRoleRemovalStep(TransitionStep):
    """Pipeline step to remove all roles when a player is banned"""

    async def execute(
        self,
        entity: Player,
        old_status: str,  # noqa: ARG002
        new_status: str,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
        **context,
    ) -> None:
        if new_status != PlayerStatus.BANNED.value:
            return  # Only act on ban transitions

        # Get all player roles
        stmt = select(PlayerRole).where(PlayerRole.player_id == entity.id)
        result = await session.execute(stmt)
        player_roles = result.scalars().all()

        # Delete all roles
        LOG.info(f"Removing {len(player_roles)} roles from banned player {entity.id}")
        for player_role in player_roles:
            await session.delete(player_role)


class PlayerUnbanRestoreStep(TransitionStep):
    """Pipeline step to restore player status when unbanned"""

    async def execute(
        self,
        entity: Player,
        old_status: str,
        new_status: str,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
        **context,
    ) -> None:
        if (
            old_status != PlayerStatus.BANNED.value
            or new_status != PlayerStatus.ACTIVE.value
        ):
            return  # Only act on unban transitions

        # In a real implementation, you might restore default roles
        # or notify teams that the player is available again

        # This is a basic example of what could be done
        LOG.info(f"Restoring player {entity.id} after ban")

        # Setup basic user role
        from auth.service.auth import AuthService

        auth_service: AuthService = context.get("auth_service")
        if auth_service:
            user_role = await auth_service.get_role_by_name("user", session)
            if user_role:
                LOG.info(f"Re-assigning basic user role to unbanned player {entity.id}")
                # Create the player_role record
                player_role = PlayerRole(
                    player_id=entity.id,
                    role_id=user_role.id,
                    scope_type=ScopeType.GLOBAL,
                )
                session.add(player_role)

