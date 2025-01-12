from typing import List, Optional, Tuple
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
import uuid
from datetime import datetime

from src.teams.models import Team, TeamCaptain, Roster
from src.teams.schemas import TeamCreate, TeamUpdate
from src.auth.models import Player
from src.competitions.models.seasons import Season
from src.audit.service import AuditService

class TeamServiceError(Exception):
    """Base exception for team service errors"""
    pass

class TeamService:
    def __init__(self):
        self.audit_service = AuditService()

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

    async def get_all_teams(self, session: AsyncSession) -> List[Team]:
        """Retrieves all teams ordered by creation date"""
        stmt = select(Team).order_by(desc(Team.created_at))
        result = await session.exec(stmt)
        return result.all()
    
    async def get_team_by_name(self, name: str, session: AsyncSession) -> Optional[Team]:
        """Retrieves a team by name"""
        stmt = select(Team).where(Team.name == name)
        result = await session.exec(stmt)
        return result.first()

    async def get_team_by_id(self, id: uuid.UUID, session: AsyncSession) -> Optional[Team]:
        """Retrieves a team by ID"""
        stmt = select(Team).where(Team.id == id)
        result = await session.exec(stmt)
        return result.first()

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
        team_data: TeamCreate,
        captain: Player,
        actor: Player,
        logo_path: Optional[str],
        session: AsyncSession
    ) -> Team:
        """Creates a new team and assigns initial captain"""
        # Create the team
        team_dict = team_data.model_dump()
        new_team = Team(
            **team_dict,
            logo=logo_path,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(new_team)
        await session.flush()  # Get ID before creating captain

        # Create the captain relationship
        team_captain = TeamCaptain(
            team_id=new_team.id,
            player_uid=captain.uid,
            created_at=datetime.now()
        )
        session.add(team_captain)
        
        return new_team

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
        result = await session.exec(stmt)
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
        result = await session.exec(stmt)
        return result.all()

    async def player_is_team_captain(self, player: Player, team: Team, session: AsyncSession) -> bool:
        """Checks if a player is captain of a team"""
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_uid == player.uid
        )
        result = await session.exec(stmt)
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