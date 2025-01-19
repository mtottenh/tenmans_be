
from typing import Dict, List, Optional
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import count
import uuid
from datetime import datetime
from teams.models import Team, Roster
from auth.models import Player
from competitions.models.seasons import Season
from audit.service import AuditService


class RosterServiceError(Exception):#
    """Base exception for roster operations"""
    pass

class RosterService:
    def __init__(self, audit_service: Optional[AuditService] = None):
        self.audit_service = audit_service or AuditService()

    def _roster_audit_details(self, roster: Roster, details: Optional[Dict] = None) -> Dict:
        """Extract audit details from a roster operation"""
        audit_data = {
            "team_id": str(roster.team_id),
            "player_id": str(roster.player_id),
            "season_id": str(roster.season_id),
            "timestamp": datetime.now().isoformat(),
            "status": "active" if not roster.pending else "pending"
        }
        if details:
            audit_data.update(details)
        return audit_data

    def _roster_id_gen(self, roster: Roster) -> uuid.UUID:
        return uuid.uuid4()
    
    @AuditService.audited_transaction(
        action_type="roster_add",
        entity_type="roster",
        details_extractor=_roster_audit_details,
        id_extractor=_roster_id_gen
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
        current_roster = await self._get_player_roster(player.id, season.id, session)
        if current_roster:
            raise RosterServiceError("Player is already on a team this season")

        # Create roster entry
        roster_entry = Roster(
            team_id=team.id,
            player_id=player.id,
            season_id=season.id,
            # Player is immediately active when added directly by captain
            pending=False
        )
        
        session.add(roster_entry)
        return roster_entry

    @AuditService.audited_deletion(
        action_type="roster_remove",
        entity_type="roster",
        details_extractor=_roster_audit_details,
        id_extractor=_roster_id_gen
    )
    async def _remove_player_from_roster(
        self,
        rostered_member: Roster,
        actor: Player,
        session: AsyncSession
    ) -> None:
        """Remove a player from team roster"""
        await session.delete(rostered_member)
        return

    async def remove_player_from_team_roster(self, team_id: str, player_id: str, season_id: str,actor: Player, session: AsyncSession):
        roster_entry = await self._get_player_roster(player_id, season_id, session, team_id=team_id)

        if not roster_entry:
            raise RosterServiceError("Player not found on team roster")

        # Check if removing team captain
        # This is handled for us by the route service.
        # is_captain = await (session.execute(
        #     select(TeamCaptain).where(
        #         TeamCaptain.team_id == team.id,
        #         TeamCaptain.player_id == player.id
        #     )
        # )).scalar_one_or_none()
        # if is_captain:
        #     raise RosterServiceError("Cannot remove team captain from roster")
        return await self._remove_player_from_roster(roster_entry, actor=actor, session=session)
        # Add removal details for audit
        # details = {
        #     "removal_reason": reason,
        #     "removed_by": str(actor.id)
        # }
        

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
        player_id: str,
        season_id: str,
        session: AsyncSession,
        team_id: Optional[str] = None
    ) -> Optional[Roster]:
        """Get player's current roster entry for season"""
        stmt = select(Roster).where(
            Roster.player_id == player_id,
            Roster.season_id == season_id
        )
        if team_id:
            stmt = stmt.where(Roster.team_id == team_id)
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
            count(Roster.player_id) >= min_players
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
    

def create_roster_service(x: Optional[AuditService] = None) -> RosterService:
    audit_serivce = x or AuditService()
    return RosterService(audit_serivce)