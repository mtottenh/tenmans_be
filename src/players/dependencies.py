from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession

from src.seasons.models import Season
from src.seasons.service import SeasonService
from .utils import decode_token
from src.db.main import get_session
from .service import PlayerService
from src.teams.service import TeamService
from .models import Player
from typing import List


class TokenBearer(HTTPBearer):
    def __init__(self, auto_error=True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        creds = await super().__call__(request=request)
        token_data = decode_token(creds.credentials)
        if token_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
            )
        self.verify_token_data(token_data)
        return token_data

    def verify_token_data(self, token_data):
        raise NotImplemented("Override this method in child classes")


class AccessTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict) -> None:
        if token_data and token_data["refresh"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Provide a valid access token",
            )


class RefreshTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict) -> None:
        if token_data and "access" in token_data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provide a valid refresh token",
            )



# TODO: Use exception handler to 
# redirect responses for website pages

# class RequiresLoginException(Exception):
#     pass

# async def redirect() -> bool:
#     raise RequiresLoginException

# @app.exception_handler(RequiresLoginException)
# async def exception_handler(request: Request, exc: RequiresLoginException) -> Response:
#     return RedirectResponse(url='/login')


player_service = PlayerService()
team_service = TeamService()
season_service = SeasonService()

async def get_current_player(
    token_details: dict = Depends(AccessTokenBearer()),
    session: AsyncSession = Depends(get_session),
) -> Player:
    print(token_details)
    player = await player_service.get_player(
        token_details["player"]["player_uid"], session
    )
    if player is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Provide a valid access token",
            )
    return player

async def get_current_season(session: AsyncSession = Depends(get_session)) -> Season:
    season = await season_service.get_active_season()
    return season
    
# TODO - How to inject the Team name & current season?
class RosterChecker:
    def __init__(self, allowed_roles: List[str]) -> None:
        self.allowed_roles = allowed_roles
    
    async def __call__(self, request: Request, current_player: Player = Depends(get_current_player)):
        
        return await team_service.player_is_on_roster(current_player)

class CaptainChecker:
    async def __call__(self, request: Request, current_player: Player = Depends(get_current_player), current_season: Season = Depends(get_current_season), session=Depends(get_session)):
        if not 'team_name' in request.path_params:
                    return False
        team = await team_service.get_team_by_name(request.path_params['team_name'], session)
        return await team_service.player_is_team_captain(current_player, team, session)


class RoleChecker:
    def __init__(self, allowed_roles: List[str]) -> None:
        self.allowed_roles = allowed_roles
    def __call__(self, current_player: Player = Depends(get_current_player)):
        if current_player.role in self.allowed_roles:
            return True
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid permission.")