from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession
from .utils import decode_token
from src.db.main import get_session
from .service import PlayerService
from src.teams.service import TeamService
from .models import Player
from typing import List


class TokenBearer(HTTPBearer):
    def __init__(self, auto_error=True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, requset: Request) -> HTTPAuthorizationCredentials | None:
        creds = await super().__call__(request=requset)
        token_data = decode_token(creds.credentials)
        if token_data is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired token"
            )
        self.verify_token_data(token_data)
        return token_data

    def verify_token_data(self, token_data):
        raise NotImplemented("Override this method in child classes")


class AccessTokenBearer(TokenBearer):

    def verify_token_data(self, token_data: dict) -> None:
        if token_data and token_data["refresh"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provide a valid access token",
            )


class RefreshTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict) -> None:
        if token_data and token_data["access"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provide a valid refresh token",
            )


player_service = PlayerService()
team_service = TeamService()

async def get_current_player(
    token_details: dict = Depends(AccessTokenBearer()),
    session: AsyncSession = Depends(get_session),
) -> Player:
    player = await player_service.get_player_by_email(
        token_details["player"]["email"], session
    )
    return player

# TODO - How to inject the Team name & current season?
class RosterChecker:
    def __init__(self, allowed_roles: List[str]) -> None:
        self.allowed_roles = allowed_roles
    
    async def __call__(self, current_player: Player = Depends(get_current_player)):
        return await team_service.player_is_on_roster(current_player)

class RoleChecker:
    def __init__(self, allowed_roles: List[str]) -> None:
        self.allowed_roles = allowed_roles
    def __call__(self, current_player: Player = Depends(get_current_player)):
        if current_player.role in self.allowed_roles:
            return True
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid permission.")