
from typing import Dict, List, Optional
from sqlalchemy import func
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import count
import uuid
from datetime import datetime
from audit.context import AuditContext
from audit.models import AuditEventType
from auth.schemas import ScopeType
from auth.service.permission import PermissionScope, PermissionService
from competitions.season.service import SeasonService, create_season_service
from status.manager.roster import initialize_roster_status_manager
from status.service import StatusTransitionService, create_status_transition_service
from teams.base_schemas import RosterStatus, TeamHistory, TeamStatus
from teams.models import Team, Roster
from auth.models import Player, Role
from competitions.models.seasons import Season
from audit.service import AuditService, create_audit_service
from teams.schemas import PlayerRosterHistory


class RosterServiceError(Exception):#
    """Base exception for roster operations"""
    pass

class RosterService:
    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        season_service: Optional[SeasonService] = None,
        status_transition_service: Optional[StatusTransitionService] = None
    ):
        self.audit_service = audit_service or AuditService()
        self.season_service = season_service or SeasonService()
        self.status_transition_service = status_transition_service or StatusTransitionService()
        
        # Register roster status manager
        roster_manager = initialize_roster_status_manager()
        self.status_transition_service.register_transition_manager("Roster", roster_manager)

    def _roster_audit_details(self, roster: Roster,  context: Dict) -> Dict:
        """Extract audit details from a roster operation"""
        audit_data = {
            "team_id": str(roster.team_id),
            "player_id": str(roster.player_id),
            "season_id": str(roster.season_id),
            "timestamp": datetime.now().isoformat(),
            "status": roster.status
        }
        # if details:
        #     audit_data.update(details)
        return audit_data

    def _roster_id_gen(self, roster: Roster) -> uuid.UUID:
        return uuid.uuid4()


    async def get_team_roster(
        self,
        team: Team,
        season: Season,
        session: AsyncSession,
        status: Optional[List[RosterStatus]] = None,
        include_all: bool = False
    ) -> List[Roster]:
        """
        Get all players on team roster for season.
        
        Args:
            team: Team to get roster for
            season: Season context
            status: Optional list of status to filter by
            include_all: If True, includes all roster entries regardless of status
            session: Database session
        """
        stmt = select(Roster).where(
            Roster.team_id == team.id,
            Roster.season_id == season.id
        ).options(
            selectinload(Roster.player).selectinload(Player.roles).selectinload(Role.permissions)
        )

        # Apply status filter if provided, otherwise default to ACTIVE only
        if status:
            stmt = stmt.where(Roster.status.in_(status))
        elif not include_all:
            stmt = stmt.where(Roster.status == RosterStatus.ACTIVE)
            
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_active_roster_count(
        self,
        team: Team,
        season: Season,
        session: AsyncSession
    ) -> int:
        """Get count of active roster players"""
        stmt = select(Roster).where(
            Roster.team_id == team.id,
            Roster.season_id == season.id,
            Roster.status == RosterStatus.ACTIVE
        )
        result = (await session.execute(stmt)).scalars()
        return len(result.all())

    async def _get_player_roster(
        self,
        player_id: str,
        season_id: str,
        session: AsyncSession,
        team_id: Optional[str] = None,
        include_inactive: bool = False
    ) -> Optional[Roster]:
        """
        Get player's current roster entry for season
        
        Args:
            player_id: Player's UUID
            season_id: Season's UUID
            team_id: Optional team UUID to filter by
            include_inactive: If True, includes non-active roster entries
            session: Database session
        """
        stmt = select(Roster).where(
            Roster.player_id == player_id,
            Roster.season_id == season_id
        )
        
        if team_id:
            stmt = stmt.where(Roster.team_id == team_id)
            
        if not include_inactive:
            stmt = stmt.where(Roster.status == RosterStatus.ACTIVE)
            
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_teams_with_min_players(
        self,
        season_id: uuid.UUID,
        min_players: int,
        session: AsyncSession
    ) -> List[Team]:
        """Get teams that have minimum required active players"""
        stmt = select(Team).join(Roster).where(
            Roster.season_id == season_id,
            Roster.status == RosterStatus.ACTIVE
        ).group_by(Team.id).having(
            func.count(Roster.player_id) >= min_players
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_suspended_players(
        self,
        team: Team,
        season: Season,
        session: AsyncSession
    ) -> List[Roster]:
        """Get all suspended players for a team"""
        return await self.get_team_roster(
            team=team,
            season=season,
            status=[RosterStatus.SUSPENDED],
            session=session
        )

    async def get_pending_players(
        self,
        team: Team,
        season: Season,
        session: AsyncSession
    ) -> List[Roster]:
        """Get all pending roster entries for a team"""
        return await self.get_team_roster(
            team=team,
            season=season,
            status=[RosterStatus.PENDING],
            session=session
        )

    async def get_teams_for_player_by_player_id(
        self,
        player_id: str,
        session: AsyncSession
    ) -> PlayerRosterHistory:
        """Get current and previous teams for a player"""
        stmt = select(Roster).where(
            Roster.player_id == player_id
        ).join(Team).options(
            selectinload(Roster.team)
        )
        result = (await session.execute(stmt)).scalars().all()
        
        if not result:
            return PlayerRosterHistory(current=None, previous=None)
            
        current_season = await self.season_service.get_active_season(session)
        
        # Get current active team if any
        current_team = next(
            (r for r in result 
             if r.season_id == current_season.id 
             and r.status == RosterStatus.ACTIVE 
             and r.team.status == TeamStatus.ACTIVE),
            None
        )
        
        # Get previous teams - include removed/past rosters and teams
        previous_teams = [
            r for r in result
            if (r.season_id != current_season.id or  # Different season
                r.status in [RosterStatus.REMOVED, RosterStatus.PAST] or  # Removed/past roster
                r.team.status != TeamStatus.ACTIVE)  # Inactive team
            and r != current_team  # Not the current team
        ]
        
        def roster_to_team_history(r: Roster) -> TeamHistory:
            if not r:
                return None
            return TeamHistory(
                team_id=r.team_id,
                name=r.team.name,
                season_id=r.season_id,
                since=r.created_at,
                status=r.team.status
            )
            
        return PlayerRosterHistory(
            current=roster_to_team_history(current_team),
            previous=[roster_to_team_history(r) for r in previous_teams] if previous_teams else None
        )

    async def validate_roster_size(
        self,
        team: Team,
        season: Season,
        min_size: int,
        max_size: int,
        session: AsyncSession
    ) -> tuple[bool, str]:
        """Validate roster size against requirements"""
        roster_size = await self.get_active_roster_count(team, season, session)
        
        if roster_size < min_size:
            return False, f"Team roster below minimum size ({roster_size}/{min_size})"
        if roster_size > max_size:
            return False, f"Team roster exceeds maximum size ({roster_size}/{max_size})"
            
        return True, "Roster size valid"


    async def change_roster_status(
        self,
        roster: Roster,
        new_status: RosterStatus,
        reason: str,
        actor: Player,
        session: AsyncSession,
        metadata: Optional[Dict] = None,
        audit_context: Optional[AuditContext] = None
    ) -> Roster:
        """Change a roster entry's status with validation and history tracking"""
        try:
            # Create scope for permission checking
            scope = PermissionScope(
                scope_type=ScopeType.TEAM,
                scope_id=roster.team_id
            )
            
            # Use status transition service
            updated_roster = await self.status_transition_service.transition_status(
                entity=roster,
                new_status=new_status,
                reason=reason,
                actor=actor,
                scope=scope,
                entity_metadata=metadata,
                session=session,
                audit_context=audit_context
            )
            
            return updated_roster
            
        except Exception as e:
            raise
        # raise RosterServiceError(f"Failed to change roster status: {str(e)}")

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type="Roster",
        details_extractor=_roster_audit_details
    )
    async def add_player_to_roster(
        self,
        team: Team,
        player: Player,
        season: Season,
        actor: Player,
        session: AsyncSession,
        details: Optional[Dict] = None,
        audit_context: Optional[AuditContext] = None
    ) -> Roster:
        """Add a player to team roster"""
        # Check if player is already on a team this season
        current_roster = await self._get_player_roster(player.id, season.id, session)
        if current_roster:
            raise RosterServiceError("Player is already on a team this season")

        # Create roster entry
        roster_entry = Roster(
            team_id=team.id,
            player_id=player.id,
            season_id=season.id,
            status=RosterStatus.PENDING 
        )
        
        session.add(roster_entry)
        await session.flush()
        await session.refresh(roster_entry)
        # Record the status change in history
        metadata = {
            "action": "roster_add",
            "season_id": str(season.id),
            **(details or {})
        }
        
        await self.change_roster_status(
            roster=roster_entry,
            new_status=RosterStatus.ACTIVE,
            reason="Initial roster addition",
            actor=actor,
            session=session,
            metadata=metadata,
            audit_context=audit_context
        )
        await session.refresh(roster_entry)
        
        return roster_entry

    async def remove_player_from_team_roster(
        self,
        team_id: str,
        player_id: str,
        season_id: str,
        actor: Player,
        session: AsyncSession,
        reason: str = "Removed from roster",
        audit_context: Optional[AuditContext] = None
    ) -> None:
        """Remove a player from team roster"""
        roster_entry = await self._get_player_roster(
            player_id,
            season_id,
            session,
            team_id=team_id
        )

        if not roster_entry:
            raise RosterServiceError("Player not found on team roster")

        # Change status to REMOVED instead of deleting
        await self.change_roster_status(
            roster=roster_entry,
            new_status=RosterStatus.REMOVED,
            reason=reason,
            actor=actor,
            session=session,
            metadata={"action": "roster_remove"},
            audit_context=audit_context
        )

    async def suspend_roster_member(
        self,
        roster: Roster,
        reason: str,
        actor: Player,
        session: AsyncSession,
        metadata: Optional[Dict] = None,
        audit_context: Optional[AuditContext] = None
    ) -> Roster:
        """Suspend a roster member"""
        return await self.change_roster_status(
            roster=roster,
            new_status=RosterStatus.SUSPENDED,
            reason=reason,
            actor=actor,
            session=session,
            metadata={"action": "roster_suspend", **(metadata or {})},
            audit_context=audit_context
        )

    async def reactivate_roster_member(
        self,
        roster: Roster,
        reason: str,
        actor: Player,
        session: AsyncSession,
        metadata: Optional[Dict] = None,
        audit_context: Optional[AuditContext] = None
    ) -> Roster:
        """Reactivate a suspended roster member"""
        return await self.change_roster_status(
            roster=roster,
            new_status=RosterStatus.ACTIVE,
            reason=reason,
            actor=actor,
            session=session,
            metadata={"action": "roster_reactivate", **(metadata or {})},
            audit_context=audit_context
        )

    async def get_roster_status_history(
        self,
        roster_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Dict]:
        """Get status change history for a roster entry"""
        return await self.status_transition_service.get_status_history(
            entity_type="Roster",
            entity_id=roster_id,
            session=session
        )

def create_roster_service(audit_service: Optional[AuditService] = None, 
                          season_service: Optional[SeasonService] = None,
                          permission_service: Optional[PermissionService] = None,
                          status_transition_service: Optional[StatusTransitionService] = None
                          ) -> RosterService:
    audit_serivce = audit_service or create_audit_service()
    season_service = season_service or create_season_service()
    status_transition_service = status_transition_service or create_status_transition_service(audit_service, permission_service)
    return RosterService(audit_serivce, season_service, status_transition_service)