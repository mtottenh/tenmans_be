from typing import Annotated, List, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession
from db.main import get_session
from auth.models import Player
from auth.service import AuthService, PermissionScope, ScopeType
from pydantic import BaseModel
import uuid
import logging
import pprint

LOG = logging.getLogger("uvicorn.error")
class TokenData(BaseModel):
    """Internal model for decoded token data"""
    player_uid: str
    auth_type: str
    exp: int
    is_refresh: bool = False

class JWTBearer(HTTPBearer):
    """Base JWT token bearer authentication"""
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
        self.auth_service = AuthService()

    async def __call__(self, request: Request) -> TokenData:
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        token_data = self.auth_service.verify_token(credentials.credentials)
        
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
            
        return TokenData(**token_data)

class AccessTokenBearer(JWTBearer):
    """Specifically validates access tokens"""
    async def __call__(self, request: Request) -> TokenData:
        token_data = await super().__call__(request)
        if token_data.is_refresh:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token required"
            )
        return token_data

class RefreshTokenBearer(JWTBearer):
    """Specifically validates refresh tokens"""
    async def __call__(self, request: Request) -> TokenData:
        token_data = await super().__call__(request)
        if not token_data.is_refresh:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token required"
            )
        return token_data

async def get_current_player(
    token_data: TokenData = Depends(AccessTokenBearer()),
    session: AsyncSession = Depends(get_session)
) -> Player:
    """Gets the current authenticated player"""
    auth_service = AuthService()
    player = await auth_service.get_player_by_uid(token_data.player_uid, session)
    
    if not player:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Player not found"
        )
    LOG.info(f"PLAYER: {pprint.pformat(player)}")
    return player

class ScopedPermissionChecker:
    """Checks if a player has required permissions within a specific scope"""
    def __init__(
        self,
        required_permissions: List[str],
        scope_type: Optional[ScopeType] = None
    ):
        self.required_permissions = required_permissions
        self.scope_type = scope_type
        self.auth_service = AuthService()

    async def __call__(
        self,
        scope_id: Optional[uuid.UUID] = None,
        player: Player = Depends(get_current_player),
        session: AsyncSession = Depends(get_session)
    ) -> bool:
        """
        Check permissions with optional scope.
        If scope_type is None, checks for global permissions only.
        If scope_type is provided but scope_id is None, checks for any permission in that scope type.
        """
        scope = None
        if self.scope_type:
            scope = PermissionScope(self.scope_type, scope_id)

        has_permissions = await self.auth_service.verify_permissions(
            player,
            self.required_permissions,
            scope,
            session
        )
        
        if not has_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return True

class GlobalPermissionChecker(ScopedPermissionChecker):
    """Checks for global permissions only"""
    def __init__(self, required_permissions: List[str]):
        super().__init__(required_permissions, None)

class TeamPermissionChecker(ScopedPermissionChecker):
    """Checks for team-scoped permissions"""
    def __init__(self, required_permissions: List[str]):
        super().__init__(required_permissions, ScopeType.TEAM)

class TournamentPermissionChecker(ScopedPermissionChecker):
    """Checks for tournament-scoped permissions"""
    def __init__(self, required_permissions: List[str]):
        super().__init__(required_permissions, ScopeType.TOURNAMENT)


class RoleChecker:
    """Checks for a player being one of a list of roles"""
    def __init__(self, required_roles: List[str]):
        self.required_roles=required_roles
        self.auth_service = AuthService()

    async def __call__(self, player: Player = Depends(get_current_player),
        session: AsyncSession = Depends(get_session)) -> bool:
            has_role = await self.auth_service.verify_role(player, self.required_roles, session)


# Type alias for dependency injection
CurrentPlayer = Annotated[Player, Depends(get_current_player)]

# Example global permission checkers

#GlobalPermissionChecker(["league_admin"])
require_moderator = GlobalPermissionChecker(["moderator"])
require_user = GlobalPermissionChecker(["user"])


# Example team permission checkers
require_team_management = TeamPermissionChecker(["manage_teams"])
require_team_roster = TeamPermissionChecker(["manage_roster"])
require_team_captain = TeamPermissionChecker(["team_captain"])

# Example tournament permission checkers
require_tournament_management = TournamentPermissionChecker(["manage_tournaments"])
require_tournament_admin = TournamentPermissionChecker(["tournament_admin"])

# Example Role based checkers (not advised..)
require_admin = RoleChecker(['league_admin'])