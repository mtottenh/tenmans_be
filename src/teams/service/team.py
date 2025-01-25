
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from sqlalchemy.orm import selectinload
import uuid
from datetime import datetime

from audit.context import AuditContext
from auth.schemas import ScopeType
from auth.service.permission import PermissionService
from competitions.models.tournaments import RegistrationStatus, TournamentRegistration
from competitions.season.service import SeasonService
from status.manager.team import initialize_team_status_manager
from status.service import StatusTransitionService
from teams.models import Team, TeamCaptain, Roster, TeamStatus
from teams.schemas import PlayerRosterHistory, TeamHistory, TeamDetailed
from teams.base_schemas import RosterStatus, TeamCaptainStatus, TeamUpdate
from auth.models import Player, Role
from audit.service import AuditService, AuditEventType
from teams.service.captain import CaptainService
from teams.service.roster import RosterService
import logging
LOG= logging.getLogger('uvicorn.error')


class TeamServiceError(Exception):
    """Base exception for team service errors"""
    pass

# TODO - delegate methods to roster service.
class TeamService:
    def __init__(self, 
                 season_service: Optional[SeasonService] = None, 
                 audit_service: Optional[AuditService] = None, 
                 captain_service: Optional[CaptainService] = None,
                 roster_service: Optional[RosterService] = None,
                status_transition_service: Optional[StatusTransitionService] = None
                ):
        self.audit_service = audit_service or AuditService()
        self.season_service = season_service or SeasonService()
        self.captain_service = captain_service or CaptainService()
        self.roster_service = roster_service or RosterService(audit_service)

        # Initialize status transition service and manager
        self.status_transition_service = status_transition_service or StatusTransitionService()
        team_status_manager = initialize_team_status_manager()
        self.status_transition_service.register_transition_manager("Team", team_status_manager)

    # Audit detail extractors
    def _team_audit_details(self, team: Team,  context: Optional[Dict] = None) -> dict:
        """Extracts audit details from a team operation"""
        return {
            "team_id": str(team.id),
            "team_name": team.name,
            "created_at": team.created_at.isoformat() if team.created_at else None,
            "updated_at": team.updated_at.isoformat() if team.updated_at else None
        }


    async def get_all_teams(
        self,
        session: AsyncSession,
        include_inactive: bool = False,
        status_filter: Optional[List[TeamStatus]] = None,
        skip: int = 0,
        limit: Optional[int] = None
    ) -> Tuple[List[Team], int]:
        """
        Retrieves all teams ordered by creation date with pagination
        
        Args:
            session: Database session
            include_inactive: If True, includes all teams regardless of status
            status_filter: Optional list of specific statuses to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            Tuple of (teams list, total count)
        """
        # Base query
        query = select(Team)
        
        # Apply status filtering
        if status_filter:
            query = query.where(Team.status.in_(status_filter))
        elif not include_inactive:
            query = query.where(Team.status == TeamStatus.ACTIVE)
        
        # Get total count before pagination
        count_query = select(func.count()).select_from(query)
        total = (await session.execute(count_query)).scalar()
        
        # Apply pagination and eager loading
        query = (query
                .order_by(desc(Team.created_at))
                .offset(skip)
                .options(
                    selectinload(Team.rosters)
                    .selectinload(Roster.player)
                    .selectinload(Player.roles)
                    .selectinload(Role.permissions),
                    selectinload(Team.captains)
                    .selectinload(TeamCaptain.player)
                    .selectinload(Player.roles)
                    .selectinload(Role.permissions)
                ))
        
        if limit is not None:
            query = query.limit(limit)
            
        result = (await session.execute(query)).scalars()
        return result.all(), total

    async def get_team_by_name(
        self,
        name: str,
        session: AsyncSession,
        include_inactive: bool = False,
        status_filter: Optional[List[TeamStatus]] = None
    ) -> Optional[Team]:
        """
        Retrieves a team by name
        
        Args:
            name: Team name to search for
            session: Database session
            include_inactive: If True, searches all teams regardless of status
            status_filter: Optional list of specific statuses to filter by
        """
        # Base query
        stmt = select(Team).where(Team.name == name)
        
        # Apply status filtering
        if status_filter:
            stmt = stmt.where(Team.status.in_(status_filter))
        elif not include_inactive:
            stmt = stmt.where(Team.status == TeamStatus.ACTIVE)
            
        # Add eager loading
        stmt = stmt.options(
            selectinload(Team.rosters)
            .selectinload(Roster.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions),
            selectinload(Team.captains)
            .selectinload(TeamCaptain.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_team_by_id(
        self,
        team_id: uuid.UUID,
        session: AsyncSession,
        include_inactive: bool = False,
        status_filter: Optional[List[TeamStatus]] = None
    ) -> Optional[Team]:
        """
        Retrieves a team by ID
        
        Args:
            team_id: ID of team to retrieve
            session: Database session
            include_inactive: If True, searches all teams regardless of status
            status_filter: Optional list of specific statuses to filter by
        """
        # Base query
        stmt = select(Team).where(Team.id == str(team_id))
        
        # Apply status filtering
        if status_filter:
            stmt = stmt.where(Team.status.in_(status_filter))
        elif not include_inactive:
            stmt = stmt.where(Team.status == TeamStatus.ACTIVE)
            
        # Add eager loading
        stmt = stmt.options(
            selectinload(Team.rosters)
            .selectinload(Roster.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions),
            selectinload(Team.captains)
            .selectinload(TeamCaptain.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_active_teams_for_tournament(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Team]:
        """
        Get all active teams registered for a tournament
        
        Args:
            tournament_id: Tournament ID
            session: Database session
        """
        stmt = select(Team).join(
            TournamentRegistration
        ).where(
            TournamentRegistration.tournament_id == tournament_id,
            TournamentRegistration.status == RegistrationStatus.APPROVED,
            Team.status == TeamStatus.ACTIVE
        ).options(
            selectinload(Team.rosters)
            .selectinload(Roster.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions),
            selectinload(Team.captains)
            .selectinload(TeamCaptain.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_teams_by_season(
        self,
        season_id: uuid.UUID,
        session: AsyncSession,
        include_inactive: bool = False
    ) -> List[Team]:
        """
        Get all teams that participated in a season
        
        Args:
            season_id: Season ID
            session: Database session
            include_inactive: If True, includes inactive teams
        """
        stmt = select(Team).join(
            Roster
        ).where(
            Roster.season_id == season_id
        )
        
        if not include_inactive:
            stmt = stmt.where(Team.status == TeamStatus.ACTIVE)
            
        stmt = stmt.options(
            selectinload(Team.rosters)
            .selectinload(Roster.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions),
            selectinload(Team.captains)
            .selectinload(TeamCaptain.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def team_exists(
        self,
        name: str,
        session: AsyncSession,
        include_inactive: bool = True
    ) -> bool:
        """
        Check if a team exists by name
        
        Args:
            name: Team name to check
            session: Database session
            include_inactive: If True, checks all teams regardless of status
        """
        team = await self.get_team_by_name(
            name,
            session,
            include_inactive=include_inactive
        )
        return team is not None
    
    async def get_all_teams_with_details(self, session: AsyncSession, include_disbanded: bool = False) -> List[TeamDetailed]:
        """Retrieves all teams with roster and captain details"""
        stmt = select(Team)
        if not include_disbanded:
            stmt = stmt.where(Team.status == TeamStatus.ACTIVE)
        stmt = stmt.order_by(desc(Team.created_at)).options(
            selectinload(Team.rosters)
            .selectinload(Roster.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions),
            selectinload(Team.captains)
            .selectinload(TeamCaptain.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = await session.execute(stmt)
        teams: List[Team] = result.scalars().all()
        
        # Get active season for roster counts
        season = await self.season_service.get_active_season(session)
        
        detailed_teams = []
        for team in teams:
            # Load relationships
            roster = team.rosters
            captains = team.captains
            
            detailed_teams.append(TeamDetailed(
                id=team.id,
                name=team.name,
                logo=team.logo,
                created_at=team.created_at,
                updated_at=team.updated_at,
                recruitment_status=team.recruitment_status,
                rosters=roster,
                captains=captains
            ))
        
        return detailed_teams

    async def team_exists(self, name: str, session: AsyncSession) -> bool:
        """Checks if a team exists by name"""
        team = await self.get_team_by_name(name, session)
        return team is not None
    @AuditService.audited_transaction(
            action_type=AuditEventType.CREATE,
            entity_type='Team',
            details_extractor=_team_audit_details
    )
    async def create_team(
        self,
        name: str,
        captain: Player,
        actor: Player,
        logo_path: Optional[str],
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Team:
        new_team = Team(
            name=name,
            logo=logo_path,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(new_team)
        await session.flush()
        await session.refresh(new_team)
        LOG.info("Created Team")
        cur_season = await self.season_service.get_active_season(session)
        LOG.info("About to create captain")
        team_captain = await self.captain_service.create_captain(new_team,
                                                                    captain,
                                                                    actor=captain,
                                                                    session=session,
                                                                    is_initial_captain=True,
                                                                    audit_context=audit_context)
        LOG.info(f"State: team {new_team} captain {captain} season: {cur_season}")
        cur_season = await self.season_service.get_active_season(session)
        await session.refresh(new_team)
        await session.refresh(captain)
        LOG.info("Created Captain")

        await self.roster_service.add_player_to_roster(
            team=new_team,
            player=captain,
            season=cur_season,
            actor=captain,
            session=session,
            details={'reason' : "Initial team creation"},
            audit_context=audit_context
        )
        LOG.info("Added player to roster")
        await session.flush()
        await session.refresh(team_captain)
        await session.refresh(actor)
        await session.refresh(new_team)
        return new_team

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Team",
        details_extractor=_team_audit_details
    )
    async def update_team(
        self,
        team: Team,
        update_data: TeamUpdate,
        actor: Player,
        logo_path: Optional[str],
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Team:
        """Updates team details"""
        update_dict = update_data.model_dump(exclude_unset=True)
        
        if logo_path:
            update_dict['logo'] = logo_path
            
        for key, value in update_dict.items():
            setattr(team, key, value)
            
        team.updated_at = datetime.now()
        session.add(team)
        return team


    async def change_team_status(
        self,
        team: Team,
        new_status: TeamStatus,
        reason: str,
        actor: Player,
        session: AsyncSession,
        entity_metadata: Optional[Dict] = None
    ) -> Team:
        """
        Change a team's status with validation and history tracking
        
        Args:
            team: Team to update
            new_status: New status to set
            reason: Reason for the change
            actor: User making the change
            entity_metadata: Additional metadata
            session: Database session
        """
        return await self.status_transition_service.transition_status(
            entity=team,
            new_status=new_status,
            reason=reason,
            actor=actor,
            entity_metadata=entity_metadata,
            session=session
        )

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Team",
        details_extractor=_team_audit_details
    )
    async def disband_team(
        self,
        team: Team,
        reason: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Team:
        """Disband a team and cleanup related data"""
        # Get and update all captains
        captains = await self.get_team_captains_by_team_id(team.id, session)
        await self._update_captain_roles(
            team=team,
            captains=captains,
            new_captain_status=TeamCaptainStatus.DISBANDED,
            should_remove_role=True,
            reason=f"Team disbanded: {reason}",
            actor=actor,
            session=session,
            audit_context=audit_context
        )
        season = await self.season_service.get_active_season(session)
        for roster in await self.roster_service.get_team_roster(team, season, session):
            await self.roster_service.change_roster_status(roster, RosterStatus.PAST, reason=f"Team disbanded: {reason}", actor=actor, session=session, audit_context=audit_context)
        # Change team status and update fields
        disbanded_team = await self.change_team_status(
            team=team,
            new_status=TeamStatus.DISBANDED,
            reason=reason,
            actor=actor,
            session=session
        )
        
        disbanded_team.disbanded_at = datetime.now()
        disbanded_team.disbanded_reason = reason
        disbanded_team.disbanded_by = actor.id
        
        session.add(disbanded_team)
        return disbanded_team

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Team",
        details_extractor=_team_audit_details
    )
    async def suspend_team(
        self,
        team: Team,
        reason: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Team:
        """Suspend a team and temporarily mark captain roles"""
        # Get and update all captains
        captains = await self.get_team_captains_by_team_id(team.id, session)
        await self._update_captain_roles(
            team=team,
            captains=captains,
            new_captain_status=TeamCaptainStatus.TEMPORARY,
            should_remove_role=False,  # Keep roles for reactivation
            reason=f"Team suspended: {reason}",
            actor=actor,
            session=session,
            audit_context=audit_context
        )

        # Change team status
        team = await self.change_team_status(
            team=team,
            new_status=TeamStatus.SUSPENDED,
            reason=reason,
            actor=actor,
            session=session
        )
        
        return team

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Team",
        details_extractor=_team_audit_details
    )
    async def reactivate_team(
        self,
        team: Team,
        reason: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Team:
        """Reactivate a suspended team and restore captain roles"""
        # Get and update all temporary captains
        captains = await self.get_team_captains_by_team_id(team.id, session)
        await self._update_captain_roles(
            team=team,
            captains=captains,
            new_captain_status=TeamCaptainStatus.ACTIVE,
            should_remove_role=False,  # Roles were kept during suspension
            reason=f"Team reactivated: {reason}",
            actor=actor,
            session=session,
            audit_context=audit_context
        )

        # Change team status
        team = await self.change_team_status(
            team=team,
            new_status=TeamStatus.ACTIVE,
            reason=reason,
            actor=actor,
            session=session
        )
        
        return team

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Team",
        details_extractor=_team_audit_details
    )
    async def archive_team(
        self,
        team: Team,
        reason: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Team:
        """Archive a team and remove captain roles"""
        # Get and update all captains
        captains = await self.get_team_captains_by_team_id(team.id, session)
        await self._update_captain_roles(
            team=team,
            captains=captains,
            new_captain_status=TeamCaptainStatus.DISBANDED,  # Use DISBANDED for archived teams
            should_remove_role=True,  # Remove roles as archived teams have no captains
            reason=f"Team archived: {reason}",
            actor=actor,
            session=session,
            audit_context=audit_context
        )

        # Change team status
        team = await self.change_team_status(
            team=team,
            new_status=TeamStatus.ARCHIVED,
            reason=reason,
            actor=actor,
            session=session
        )
        
        return team
    async def get_team_status_history(
        self,
        team_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Dict]:
        """Get status change history for a team"""
        return await self.status_transition_service.get_status_history(
            entity_type="Team",
            entity_id=team_id,
            session=session
        )
    
    async def _update_captain_roles(
        self,
        team: Team,
        captains: List[Player],
        new_captain_status: TeamCaptainStatus,
        should_remove_role: bool,
        reason: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> None:
        """Update captain roles and status for a team status change"""
        for captain in captains:
            # Update captain status
            captain_entry = await self.captain_service.get_captain(team, captain, session)
            await self.captain_service.change_captain_status(
                captain=captain_entry,
                new_status=new_captain_status,
                reason=reason,
                actor=actor,
                session=session,
                audit_context=audit_context
            )

            # Remove role if required
            if should_remove_role:
                return await self.captain_service.remove_captain(captain_entry, actor=actor, session=session, reason=reason, audit_context=audit_context)
                # captain_role = await self.role_service.get_role_by_name("team_captain", session)
                # if captain_role:
                #     await self.role_service.remove_role_from_player(
                #         player=captain,
                #         role=captain_role,
                #         scope_type=ScopeType.TEAM,
                #         scope_id=team.id,
                #         actor=actor,
                #         session=session
                #     )

    # RosterService Delegations
    async def get_active_roster_count(self, *args, **kwargs):
        return await self.roster_service.get_active_roster_count(*args, **kwargs)
    
    async def remove_player_from_team_roster(self, *args, **kwargs):
        return await self.roster_service.remove_player_from_team_roster(*args, **kwargs)
    
    async def get_teams_for_player_by_player_id(self, *args, **kwargs):
        return await self.roster_service.get_teams_for_player_by_player_id(*args, **kwargs)

    # CaptainService Delegations
    async def get_captain(self, *args, **kwargs):
        return await self.captain_service.get_captain(*args, **kwargs)
    
    async def get_team_captains_by_team_id(self, *args, **kwargs):
        return await self.captain_service.get_team_captains_by_team_id(*args, **kwargs)
    
    async def player_is_team_captain(self, *args, **kwargs):
        return await self.captain_service.player_is_team_captain(*args, **kwargs)

    async def create_captain(self, *args, **kwargs):
        return await self.captain_service.create_captain(*args, **kwargs)
    
    async def remove_captain(self, *args, **kwargs):
        return await self.captain_service.remove_captain(*args, **kwargs)
# Factory method
def create_team_service(audit_service: Optional[AuditService], 
                        roster_service: Optional[RosterService] = None,
                        season_service: Optional[SeasonService] = None,
                        captain_service: Optional[CaptainService] = None,
                        permission_service: Optional[PermissionService] = None,
                        status_transition_service: Optional[StatusTransitionService] = None
                        ) -> TeamService:
    audit_service = audit_service or AuditService()
    season_service = season_service or SeasonService()
    roster_service = roster_service or RosterService(audit_service, season_service)
    captain_service = captain_service or CaptainService()
    permission_service = permission_service or PermissionService(audit_service)
    status_transition_service = status_transition_service or StatusTransitionService(audit_service, permission_service)
    
    return TeamService(season_service, audit_service, captain_service, roster_service, status_transition_service)