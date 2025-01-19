
from typing import Dict, List, Optional
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from sqlalchemy.orm import selectinload
import uuid
from datetime import datetime

from competitions.season.service import SeasonService
from teams.models import Team, TeamCaptain, Roster, TeamStatus
from teams.schemas import PlayerRosterHistory, TeamHistory, TeamDetailed
from teams.base_schemas import TeamUpdate
from auth.models import Player, Role
from audit.service import AuditService
from teams.service.roster import RosterService




class TeamServiceError(Exception):
    """Base exception for team service errors"""
    pass

# TODO - delegate methods to roster service.
class TeamService:
    def __init__(self, 
                 season_service: Optional[SeasonService] = None, 
                 audit_service: Optional[AuditService] = None, 
                 roster_service: Optional[RosterService] = None
                ):
        self.audit_service = audit_service or AuditService()
        self.season_service = season_service or SeasonService()
        self.roster_service = roster_service or RosterService(audit_service)

    # Audit detail extractors
    def _team_audit_details(self, team: Team) -> dict:
        """Extracts audit details from a team operation"""
        return {
            "team_id": str(team.id),
            "team_name": team.name,
            "created_at": team.created_at.isoformat() if team.created_at else None,
            "updated_at": team.updated_at.isoformat() if team.updated_at else None
        }


    def _captain_audit_details(self, captain: TeamCaptain) -> dict:
        """Extracts audit details from a captain operation"""
        return {
            "team_id": str(captain.team_id),
            "player_id": str(captain.player_id),
            "created_at": captain.created_at.isoformat() if captain.created_at else None
        }

    async def get_all_teams(self, session: AsyncSession, include_disbanded: bool = False) -> List[Team]:
        """Retrieves all teams ordered by creation date"""
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

        result = (await session.execute(stmt)).scalars()
        return result.all()
    
    async def get_team_by_name(self, name: str, session: AsyncSession) -> Optional[Team]:
        """Retrieves a team by name"""
        stmt = select(Team).where(Team.name == name).options(
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

    async def get_team_by_id(self, team_id: uuid.UUID, session: AsyncSession) -> Optional[Team]:
        """Retrieves a team by ID"""
        stmt = select(Team).where(Team.id == str(team_id)).options(
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
        teams = result.scalars().all()
        
        # Get active season for roster counts
        season = await self.season_service.get_active_season(session)
        
        detailed_teams = []
        for team in teams:
            # Load relationships
            roster = team.rosters
            captains = team.captains
            
            # Count active roster members for current season
            active_roster = [r for r in roster if not r.pending and 
                            (not season or r.season_id == season.id)]
            active_roster_count = len(active_roster)
            
            detailed_teams.append(TeamDetailed(
                id=team.id,
                name=team.name,
                logo=team.logo,
                #active_roster_count=active_roster_count,
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
        action_type="team_create",
        entity_type="team",
        details_extractor=_team_audit_details
    )
    async def create_team(
        self,
        name: str,
        captain: Player,
        actor: Player,
        logo_path: Optional[str],
        session: AsyncSession
    ) -> Team:
        """Creates a new team and assigns initial captain"""
        # Create the team
        new_team = Team(
            name=name,
            logo=logo_path,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(new_team)
        await session.flush()  # Get ID before creating captain
        await session.refresh(new_team)
        team_captain = await self._create_captain_internal(new_team, captain, session)

        await session.flush()
        cur_season = await self.season_service.get_active_season(session)

        # TODO - use self.roster_service._add_to_roster_internal?
        initial_roster_entry = Roster(
            team_id=new_team.id,
            player_id=captain.id,
            season_id=cur_season.id,
            pending=False

        )
        session.add(initial_roster_entry)
        await session.flush()
        await session.refresh(initial_roster_entry)
        await session.refresh(team_captain)
        await session.refresh(actor)
        await session.refresh(new_team)
        return new_team


    async def _create_captain_internal(
            self,
            team: Team,
            player: Player,
            session: AsyncSession
    ) -> TeamCaptain:
        # Verify player isn't already captain
        is_captain = await self.player_is_team_captain(player, team, session)
        if is_captain:
            raise TeamServiceError("Player is already a captain of this team")

        new_captain = TeamCaptain(
            team_id=team.id,
            player_id=player.id,
            created_at=datetime.now()
        )
        session.add(new_captain)
        return new_captain
    
    @AuditService.audited_transaction(
        action_type="team_captain_add",
        entity_type="team",
        details_extractor=_captain_audit_details
    )
    async def create_captain(
        self,
        team: Team,
        player: Player,
        actor: Player,
        session: AsyncSession
    ) -> TeamCaptain:
        """Adds a new captain to a team"""
        new_captain = await self._create_captain_internal(team, player, session)
        return new_captain

    async def get_captain(self, team: Team, player: Player, session: AsyncSession):
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_id == player.id
        )
        result = (await session.execute(stmt)).scalars()
        captain = result.first()
        
        if not captain:
            raise TeamServiceError("Player is not a captain of this team")
        return captain
    
    @AuditService.audited_deletion(
        action_type="team_captain_remove",
        entity_type="team",
        details_extractor=_captain_audit_details
    )
    async def remove_captain(
        self,
        captain: TeamCaptain,
        actor: Player,
        session: AsyncSession
    ) -> TeamCaptain:
        """Removes a player as team captain"""
        await session.delete(captain)
        return captain

    async def get_team_captains(self, team_name: str, session: AsyncSession) -> List[Player]:
        """Gets all captains for a team"""
        stmt = select(Player).where(
            Team.name == team_name,
            Team.id == TeamCaptain.team_id,
            Player.id == TeamCaptain.player_id
        ).options(
            selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_team_captains_by_team_id(self, team_id: str, session: AsyncSession) -> List[Player]:
        """Gets all captains for a team"""
        stmt = select(Player).where(
            Team.id == team_id,
            Team.id == TeamCaptain.team_id,
            Player.id == TeamCaptain.player_id
        ).options(

            selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()
        
    async def player_is_team_captain(self, player: Player, team: Team, session: AsyncSession) -> bool:
        """Checks if a player is captain of a team"""
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_id == player.id
        )
        result = (await session.execute(stmt)).scalars()
        return result.first() is not None

    @AuditService.audited_transaction(
        action_type="team_update",
        entity_type="team",
        details_extractor=_team_audit_details
    )
    async def update_team(
        self,
        team: Team,
        update_data: TeamUpdate,
        actor: Player,
        logo_path: Optional[str],
        session: AsyncSession
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




    @AuditService.audited_transaction(
            action_type="team_disband",
            entity_type="team",
            details_extractor=_team_audit_details
    )
    async def disband_team(
        self,
        team: Team,
        reason: str,
        actor: Player,
        session: AsyncSession
    ) -> Team:
        """Disband a team while preserving history"""
        team.status = TeamStatus.DISBANDED
        team.disbanded_at = datetime.now()
        team.disbanded_reason = reason
        team.disbanded_by = actor.id
        session.add(team)
        return team


    # We never really want to call this!
    # We woul dhave to update our model to cascade dletes, intsead we should
    # use a soft-delete
    @AuditService.audited_transaction(
        action_type="team_delete",
        entity_type="team",
        details_extractor=_team_audit_details
    )
    async def delete_team(
        self,
        team: Team,
        actor: Player,
        session: AsyncSession
    ) -> Team:
        """Deletes a team and all related records"""
        await session.delete(team)
        return team  # Return team for audit logging before deletion


    async def get_teams_for_player_by_player_id(self, player_id: str, session: AsyncSession):
        stmnt = select(Roster).where(Roster.player_id == player_id).where(Roster.team_id == Team.id).options(
            selectinload(Roster.team)
        )
        result: List[Roster] = (await session.execute(stmnt)).scalars().all()
        if len(result) == 0:
            return PlayerRosterHistory(current=None, previous=None)
        current_season = await self.season_service.get_active_season(session)
        
        current_team = [ x for x in result if x.season_id == current_season.id and x.team.status == TeamStatus.ACTIVE]
        previous_team = [ x for x in result if x.season_id != current_season.id or x.team.status != TeamStatus.ACTIVE]
        current_team = current_team[0] if len(current_team) == 1 else None
        
        
        def roster_to_team_history(r: Roster) -> TeamHistory:
            if r is None:
                return None
            return TeamHistory(team_id=r.team_id,
                               name=r.team.name,
                               season_id=r.season_id,
                               since=r.created_at,
                               status=r.team.status)
        previous_rosters = [ roster_to_team_history(p) for p in previous_team ]

        return PlayerRosterHistory(
            current=roster_to_team_history(current_team),
            previous=previous_rosters if len(previous_rosters) > 0 else None
        )
    

    async def get_active_roster_count(self, *args, **kwargs):
        return await self.roster_service.get_active_roster_count(*args, **kwargs)
    
    async def remove_player_from_team_roster(self, *args, **kwargs):
        return await self.roster_service.remove_player_from_team_roster(*args, **kwargs)
    
def create_team_service(audit_service: Optional[AuditService], 
                        roster_service: Optional[RosterService] = None,
                        season_service: Optional[SeasonService] = None) -> TeamService:
    audit_service = audit_service or AuditService()
    roster_service = roster_service or RosterService(audit_service)
    season_service = season_service or SeasonService()
    return TeamService(season_service, audit_service, roster_service)