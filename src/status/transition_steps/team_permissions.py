import logging
from typing import Dict, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from auth.schemas import ScopeType
from auth.service.permission import PermissionService
from auth.service.role import RoleService
from status.pipeline import TransitionStep
from teams.base_schemas import TeamCaptainStatus, TeamStatus
from teams.models import Team, TeamCaptain

LOG = logging.getLogger('uvicorn.error')

class TeamCaptainPermissionRevokeStep(TransitionStep):
    """Pipeline step to revoke captain permissions when a team is disbanded"""
    
    def __init__(self, permission_service: PermissionService, role_service: RoleService):
        self.permission_service = permission_service
        self.role_service = role_service
    
    async def execute(
        self,
        entity: Team,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != TeamStatus.DISBANDED.value:
            return  # Only act on disband transitions
        
        # Get all captains
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == entity.id,
            TeamCaptain.status.in_([TeamCaptainStatus.ACTIVE, TeamCaptainStatus.TEMPORARY])
        )
        result = await session.execute(stmt)
        captains = result.scalars().all()
        
        # Remove captain role from each captain
        team_captain_role = await self.role_service.get_role_by_name("team_captain", session)
        if not team_captain_role:
            LOG.warning("team_captain role not found, unable to revoke permissions")
            return
            
        for captain in captains:
            LOG.info(f"Revoking captain permissions for player {captain.player_id}")
            
            # Get the player
            from auth.models import Player
            player_stmt = select(Player).where(Player.id == captain.player_id)
            player_result = await session.execute(player_stmt)
            player = player_result.scalar_one_or_none()
            
            if player:
                await self.role_service.remove_role_from_player(
                    player=player,
                    role=team_captain_role,
                    scope_type=ScopeType.TEAM,
                    scope_id=entity.id,
                    actor=actor,
                    session=session,
                    audit_context=audit_context
                )