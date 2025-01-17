from fastapi import Depends, HTTPException, Path, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import Optional
from auth.models import Player
from auth.dependencies import get_current_player
from db.main import get_session
from teams.service import TeamService
from auth.service import AuthService

team_service = TeamService()
auth_service = AuthService()

from fastapi import Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import Optional
from auth.models import Player
from auth.service import AuthService
from db.main import get_session
from teams.service import TeamService

team_service = TeamService()
auth_service = AuthService()

class CaptainCheckerBase:
    """Permission checker for team captain operations."""

    async def __call__(
        self,
        team_identifier: str,
        identifier_type: str,
        current_player: Player = Depends(get_current_player),
        session: AsyncSession = Depends(get_session)
    ) -> Player:
        """Verifies the current player is either team captain or has global admin permissions."""
        
        # First check for global admin permissions
        has_admin = await auth_service.verify_permissions(
            current_player,
            ["admin"],
            None,
            session
        )
        if has_admin:
            return current_player

        # Get team by either name or ID based on the identifier type
        team = None
        if identifier_type == "name":
            team = await team_service.get_team_by_name(team_identifier, session)
        elif identifier_type == "id":
            team = await team_service.get_team_by_id(team_identifier, session)

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )

        # Check if player is team captain
        is_captain = await team_service.player_is_team_captain(
            current_player,
            team,
            session
        )

        if not is_captain:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires team captain permission"
            )

        return current_player

class CaptainCheckerByTeamName(CaptainCheckerBase):
    """Checker for team captain validation by team name."""
    
    async def __call__(
        self,
        team_name: str = Path(...),
        current_player: Player = Depends(get_current_player),
        session: AsyncSession = Depends(get_session)
    ) -> Player:
        return await super().__call__(team_name, "name", current_player, session)


class CaptainCheckerByTeamId(CaptainCheckerBase):
    """Checker for team captain validation by team ID."""
    
    async def __call__(
        self,
        team_id: str = Path(...),
        current_player: Player = Depends(get_current_player),
        session: AsyncSession = Depends(get_session)
    ) -> Player:
        return await super().__call__(team_id, "id", current_player, session)
    
# Create dependency
require_team_captain_by_name = CaptainCheckerByTeamName()
require_team_captain_by_id = CaptainCheckerByTeamId()