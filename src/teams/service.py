from typing import Dict, List, Optional, Tuple
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.functions import count
import uuid
from datetime import datetime

from competitions.season.service import SeasonService
from teams.models import Team, TeamCaptain, Roster, TeamStatus
from teams.schemas import PlayerRosterHistory, TeamCreate, TeamHistory, TeamUpdate, TeamBasic, TeamDetailed
from auth.models import Player, Role
from competitions.models.seasons import Season
from audit.service import AuditService

season_service = SeasonService()
class TeamServiceError(Exception):
    """Base exception for team service errors"""
    pass

class TeamService:
    def __init__(self):
        self.audit_service = AuditService()
        self.roster_service = RosterService()

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
            "player_id": str(captain.player_uid),
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

    async def get_team_by_id(self, id: uuid.UUID, session: AsyncSession) -> Optional[Team]:
        """Retrieves a team by ID"""
        stmt = select(Team).where(Team.id == id).options(
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
        season = await season_service.get_active_season(session)
        
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
        cur_season = await season_service.get_active_season(session)

        # TODO - use self.roster_service._add_to_roster_internal?
        initial_roster_entry = Roster(
            team_id=new_team.id,
            player_uid=captain.uid,
            season_id=cur_season.id,
            pending=False

        )
        session.add(initial_roster_entry)
        await session.flush()
        await session.refresh(initial_roster_entry)
        await session.refresh(team_captain)
        await session.refresh(actor)
        await session.refresh(new_team)
        # TODO - do we need to 'selectinload()' on new team?
        # This is an audited transaction - so the audit module will be calling
        # commit() - does that matter? 
        # stmt = select(Team).where(Team.id == new_team.id).options(
        #     selectinload(Team.rosters)
        #     .selectinload(Roster.player)
        #     .selectinload(Player.roles)
        #     .selectinload(Role.permissions),
        #     selectinload(Team.captains)
        #     .selectinload(TeamCaptain.player)
        #     .selectinload(Player.roles)
        #     .selectinload(Role.permissions)
        # )
        # result = await session.execute(stmt)
        # new_team = result.scalars().first()

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
            player_uid=player.uid,
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

    @AuditService.audited_transaction(
        action_type="team_captain_remove",
        entity_type="team",
        details_extractor=_captain_audit_details
    )
    async def remove_captain(
        self,
        team: Team,
        player: Player,
        actor: Player,
        session: AsyncSession
    ) -> TeamCaptain:
        """Removes a player as team captain"""
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_uid == player.uid
        )
        result = (await session.execute(stmt)).scalars()
        captain = result.first()
        
        if not captain:
            raise TeamServiceError("Player is not a captain of this team")
            
        await session.delete(captain)
        return captain

    async def get_team_captains(self, team_name: str, session: AsyncSession) -> List[Player]:
        """Gets all captains for a team"""
        stmt = select(Player).where(
            Team.name == team_name,
            Team.id == TeamCaptain.team_id,
            Player.uid == TeamCaptain.player_uid
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_team_captains_by_team_id(self, team_id: str, session: AsyncSession) -> List[Player]:
        """Gets all captains for a team"""
        stmt = select(Player).where(
            Team.id == team_id,
            Team.id == TeamCaptain.team_id,
            Player.uid == TeamCaptain.player_uid
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()
        
    async def player_is_team_captain(self, player: Player, team: Team, session: AsyncSession) -> bool:
        """Checks if a player is captain of a team"""
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_uid == player.uid
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
        team.disbanded_by = actor.uid
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


    async def get_teams_for_player_by_player_id(self, player_uid: str, session: AsyncSession):
        stmnt = select(Roster).where(Roster.player_uid == player_uid).where(Roster.team_id == Team.id).options(
            selectinload(Roster.team)
        )
        result: List[Roster] = (await session.execute(stmnt)).scalars().all()
        if len(result) == 0:
            return PlayerRosterHistory(current=None, previous=None)
        current_season = await season_service.get_active_season(session)
        
        current_team = [ x for x in result if x.season_id == current_season.id]
        previous_team = [ x for x in result if x.season_id != current_season.id]
        current_team = current_team[0] if len(current_team) == 1 else None
        
        
        def roster_to_team_history(r: Roster) -> TeamHistory:
            if r is None:
                return None
            return TeamHistory(team_id=r.team_id,
                               name=r.team.name,
                               season_id=r.season_id,
                               since=r.created_at)
        previous_rosters = [ roster_to_team_history(p) for p in previous_team ]

        return PlayerRosterHistory(
            current=roster_to_team_history(current_team),
            previous=previous_rosters if len(previous_rosters) > 0 else None
        )

class RosterServiceError(Exception):#
    """Base exception for roster operations"""
    pass

class RosterService:
    def __init__(self):
        self.audit_service = AuditService()

    def _roster_audit_details(self, roster: Roster, action: str, details: Optional[Dict] = None) -> Dict:
        """Extract audit details from a roster operation"""
        audit_data = {
            "action": action,
            "team_id": str(roster.team_id),
            "player_id": str(roster.player_uid),
            "season_id": str(roster.season_id),
            "timestamp": datetime.now().isoformat(),
            "status": "active" if not roster.pending else "pending"
        }
        if details:
            audit_data.update(details)
        return audit_data

    @AuditService.audited_transaction(
        action_type="roster_add",
        entity_type="roster",
        details_extractor=_roster_audit_details
    )
    async def add_player_to_roster(
        self,
        team: Team,
        player: Player,
        season: Season,
        actor: Player,
        session: AsyncSession,
        details: Optional[Dict] = None
    ) -> Roster:
        """Add a player to team roster"""
        # Check if player is already on a team this season
        current_roster = await self._get_player_roster(player, season, session)
        if current_roster:
            raise RosterServiceError("Player is already on a team this season")

        # Create roster entry
        roster_entry = Roster(
            team_id=team.id,
            player_uid=player.uid,
            season_id=season.id,
            # Player is immediately active when added directly by captain
            pending=False
        )
        
        session.add(roster_entry)
        return roster_entry

    @AuditService.audited_transaction(
        action_type="roster_remove",
        entity_type="roster",
        details_extractor=_roster_audit_details
    )
    async def remove_player_from_roster(
        self,
        team: Team,
        player: Player,
        season: Season,
        actor: Player,
        reason: str,
        session: AsyncSession
    ) -> None:
        """Remove a player from team roster"""
        roster_entry = await self._get_player_roster(player, season, session)
        if not roster_entry or roster_entry.team_id != team.id:
            raise RosterServiceError("Player not found on team roster")

        # Check if removing team captain
        is_captain = await (session.execute(
            select(TeamCaptain).where(
                TeamCaptain.team_id == team.id,
                TeamCaptain.player_uid == player.uid
            )
        )).scalar_one_or_none()
        
        if is_captain:
            raise RosterServiceError("Cannot remove team captain from roster")

        # Add removal details for audit
        details = {
            "removal_reason": reason,
            "removed_by": str(actor.uid)
        }
        
        await session.delete(roster_entry)
        return roster_entry, details

    async def get_team_roster(
        self,
        team: Team,
        season: Season,
        session: AsyncSession,
        include_pending: bool = False
    ) -> List[Roster]:
        """Get all players on team roster for season"""
        stmt = select(Roster).where(
            Roster.team_id == team.id,
            Roster.season_id == season.id
        )
        if not include_pending:
            stmt = stmt.where(Roster.pending == False)
            
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
            Roster.pending == False
        )
        result = (await session.execute(stmt)).scalars()
        return len(result.all())

    async def get_team_roster_history(
        self,
        team: Team,
        session: AsyncSession
    ) -> List[Dict]:
        """Get roster change history from audit logs"""
        # Fetch audit logs for roster changes
        audit_logs = await self.audit_service.get_entity_audit_logs(
            entity_type="roster",
            entity_id=team.id,
            session=session
        )
        
        # Transform logs into roster history
        history = []
        for log in audit_logs:
            history.append({
                "timestamp": log.created_at,
                "action": log.action_type,
                "player_id": log.details.get("player_id"),
                "actor_id": log.actor_id,
                "details": log.details
            })
            
        return history

    async def _get_player_roster(
        self,
        player: Player,
        season: Season,
        session: AsyncSession
    ) -> Optional[Roster]:
        """Get player's current roster entry for season"""
        stmt = select(Roster).where(
            Roster.player_uid == player.uid,
            Roster.season_id == season.id
        )
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
            Roster.pending == False
        ).group_by(Team.id).having(
            count(Roster.player_uid) >= min_players
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

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