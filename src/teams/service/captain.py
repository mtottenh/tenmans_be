from datetime import datetime
from typing import Dict, List, Optional
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload



from audit.context import AuditContext
from audit.models import AuditEventType
from audit.service import AuditService, create_audit_service
from auth.models import Player, Role
from auth.schemas import ScopeType
from auth.service.permission import PermissionService, create_permission_service
from auth.service.role import RoleService, create_role_service
from status.manager.captain import initialize_captain_status_manager
from status.service import StatusTransitionService, create_status_transition_service
from teams.base_schemas import TeamCaptainStatus
from teams.models import Team, TeamCaptain


class CaptainServiceError(Exception):
    pass

class CaptainService:
    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        permission_service: Optional[PermissionService] = None,
        role_service: Optional[RoleService] = None,
        status_transition_service: Optional[StatusTransitionService] = None
    ):
        self.audit_service = audit_service or create_audit_service()
        self.permission_service = permission_service or create_permission_service(self.audit_service)
        self.role_service = role_service or create_role_service(self.role_service)
        self.status_transition_service = status_transition_service or create_status_transition_service(
            self.audit_service,
            self.permission_service
        )

        # Register captain status manager
        captain_manager = initialize_captain_status_manager()
        self.status_transition_service.register_transition_manager("TeamCaptain", captain_manager)


    def _captain_audit_details(self, captain: TeamCaptain,  context: Dict) -> dict:
        """Extracts audit details from a captain operation"""
        return {
            "team_id": str(captain.team_id),
            "player_id": str(captain.player_id),
            "status": captain.status,
            "created_at": captain.created_at.isoformat() if captain.created_at else None
        }

    async def _create_captain_internal(
            self,
            team: Team,
            player: Player,
            session: AsyncSession
    ) -> TeamCaptain:
        # Check for existing captain record
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_id == player.id
        )
        result = (await session.execute(stmt)).scalars().first()
        
        if result:
            # If record exists, only allow if it's in REMOVED status
            if result.status != TeamCaptainStatus.REMOVED:
                raise CaptainServiceError("Player is already a captain of this team")
            return result
        
        # Create new record as ACTIVE if none exists
        new_captain = TeamCaptain(
            team_id=team.id,
            player_id=player.id,
            status=TeamCaptainStatus.ACTIVE,
            created_at=datetime.now()
        )
        session.add(new_captain)
        return new_captain

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type="TeamCaptain",
        details_extractor=_captain_audit_details
    )
    async def create_captain(
        self,
        team: Team,
        player: Player,
        actor: Player,
        session: AsyncSession,
        is_initial_captain: bool = False,
        audit_context: Optional[AuditContext] = None
    ) -> TeamCaptain:
        """Adds a new captain to a team or reactivates a removed captain"""
        captain = await self._create_captain_internal(team, player, session)
        await session.flush()
        await session.refresh(player)
        await session.refresh(team)

        # Assign role for both new captains and reactivating removed captains
        captain_role = await self.role_service.get_role_by_name('team_captain', session)
        await self.role_service.assign_role(
            player, 
            captain_role, 
            ScopeType.TEAM, 
            team.id, 
            actor=actor, 
            session=session, 
            audit_context=audit_context
        )
        await session.refresh(captain)
        # Only need to change status if reactivating a removed captain
        if captain.status == TeamCaptainStatus.REMOVED:
            await self.change_captain_status(
                captain=captain,
                new_status=TeamCaptainStatus.ACTIVE,
                reason="Captain reactivation",
                actor=actor,
                session=session,
                metadata={"is_initial_captain": is_initial_captain},
                audit_context=audit_context
            )
        
        return captain

    async def change_captain_status(
        self,
        captain: TeamCaptain,
        new_status: TeamCaptainStatus,
        reason: str,
        actor: Player,
        session: AsyncSession,
        metadata: Optional[Dict] = None,
        audit_context: Optional[AuditContext] = None
    ) -> TeamCaptain:
        """Change a captain's status using the transition service"""
        return await self.status_transition_service.transition_status(
            entity=captain,
            new_status=new_status,
            reason=reason,
            actor=actor,
            entity_metadata=metadata,
            session=session,
            audit_context=audit_context
        )

    async def get_captain(self, team: Team, player: Player, session: AsyncSession):
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_id == player.id
        )
        result = (await session.execute(stmt)).scalars()
        captain = result.first()
        
        if not captain:
            raise CaptainServiceError("Player is not a captain of this team")
        return captain

    async def get_active_captains(
        self,
        team: Team,
        session: AsyncSession
    ) -> List[TeamCaptain]:
        """Get all active captains for a team"""
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.status == TeamCaptainStatus.ACTIVE
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()
    
    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TeamCaptain",
        details_extractor=_captain_audit_details
    )
    async def remove_captain(
        self,
        captain: TeamCaptain,
        actor: Player,
        session: AsyncSession,
        reason: str = "Captain removed",
        audit_context: Optional[AuditContext] = None
    ) -> TeamCaptain:
        """Removes a player as team captain"""
        team_captain_role = await self.role_service.get_role_by_name('team_captain', session)
        player = await session.get(Player, captain.player_id)
        await self.role_service.remove_role_from_player(player, team_captain_role, ScopeType.TEAM, captain.team_id, actor=actor, session=session, audit_context=audit_context)
        return await self.change_captain_status(
            captain=captain,
            new_status=TeamCaptainStatus.REMOVED,
            reason=reason,
            actor=actor,
            session=session,
            audit_context=audit_context
        )

    async def get_team_captains(
        self,
        team_name: str,
        session: AsyncSession
    ) -> List[Player]:
        """Gets all captains for a team"""
        stmt = select(Player).where(
            Team.name == team_name,
            Team.id == TeamCaptain.team_id,
            Player.id == TeamCaptain.player_id,
            TeamCaptain.status.in_([TeamCaptainStatus.ACTIVE, TeamCaptainStatus.TEMPORARY])
        ).options(
            selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_team_captains_by_team_id(
        self,
        team_id: str,
        session: AsyncSession
    ) -> List[Player]:
        """Gets all captains for a team"""
        stmt = select(Player).where(
            Team.id == team_id,
            Team.id == TeamCaptain.team_id,
            Player.id == TeamCaptain.player_id,
            TeamCaptain.status.in_([TeamCaptainStatus.ACTIVE, TeamCaptainStatus.TEMPORARY, TeamCaptainStatus.PENDING])
        ).options(
            selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()
        
    async def player_is_team_captain(
        self,
        player: Player,
        team: Team,
        session: AsyncSession
    ) -> bool:
        """Checks if a player is captain of a team"""
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_id == player.id,
            TeamCaptain.status.in_([TeamCaptainStatus.ACTIVE, TeamCaptainStatus.TEMPORARY])
        )
        result = (await session.execute(stmt)).scalars()
        return result.first() is not None


def create_captain_service(
    audit_service: Optional[AuditService] = None,
    permission_service: Optional[PermissionService] = None,
    role_service: Optional[RoleService] = None,
    status_transition_service: Optional[StatusTransitionService] = None
) -> CaptainService:
    audit_service = audit_service or create_audit_service()
    permission_service = permission_service or create_permission_service(audit_service)
    role_service = role_service or create_role_service(permission_service)
    status_transition_service = status_transition_service or create_status_transition_service(
        audit_service,
        permission_service
    )
    return CaptainService(audit_service, permission_service, role_service, status_transition_service)