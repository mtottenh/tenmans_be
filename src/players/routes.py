from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from src.db.main import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from src.players.service import PlayerService
from src.players.models import Player
from src.players.schemas import PlayerUpdateModel, PlayerCreateModel, PlayerLoginModel
from src.players.dependencies import (
    AccessTokenBearer,
    RefreshTokenBearer,
    RoleChecker,
    get_current_player,
)
from datetime import timedelta, datetime
from typing import List
from .utils import create_access_token, decode_token, verify_password

player_router = APIRouter(prefix="/players")
player_service = PlayerService()
access_token_bearer = AccessTokenBearer()
refresh_token_bearer = RefreshTokenBearer()
admin_checker = RoleChecker(["admin", "user"])


REFRESH_TOKEN_EXPIRY = 2


@player_router.post(
    "/signup", status_code=status.HTTP_201_CREATED, response_model=Player
)
async def create_player(
    player_data: PlayerCreateModel, session: AsyncSession = Depends(get_session)
) -> dict:
    email = player_data.email
    player_exists = await player_service.player_exists(email, session)
    if player_exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Player with email '{email}' already exists",
        )
    new_player = await player_service.create_player(player_data, session)
    return new_player


@player_router.post("/login")
async def login_player(
    login_data: PlayerLoginModel, session: AsyncSession = Depends(get_session)
):
    player = await player_service.get_player_by_email(login_data.email, session)

    if player is not None:
        password_valid = verify_password(login_data.password, player.password_hash)

        if password_valid:
            access_token = create_access_token(
                player_data={
                    "email": player.email,
                    "player_uid": str(player.uid),
                    "role": player.role,
                }
            )
            refresh_token = create_access_token(
                player_data={
                    "email": player.email,
                    "player_uid": str(player.uid),
                },
                refresh=True,
                expiry=timedelta(days=REFRESH_TOKEN_EXPIRY),
            )
            return JSONResponse(
                content={
                    "message": "Login successful",
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "player": {"email": player.email, "uid": str(player.uid)},
                }
            )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Invalid playername/Password"
    )

@player_router.post("/refresh")
async def get_new_access_token(token_details: dict = Depends(refresh_token_bearer), session: AsyncSession  = Depends(get_session)):
    expiry_date = token_details["exp"]
    if datetime.fromtimestamp(expiry_date) > datetime.now():
        player = await player_service.player_exists_by_id(token_details['player']['player_uid'], session)
        if not player:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Refresh Token")
        new_access_token = create_access_token(player_data=token_details["player"])
        return JSONResponse(content={"access_token": new_access_token})
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired refresh token",
    )

@player_router.get("/", response_model=List[Player])
async def get_players(
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    players = await player_service.get_all_players(session)
    return players


@player_router.get("/me")
async def get_current_player_route(player: Player = Depends(get_current_player)):
    return player



@player_router.get("/name/{player_name}", response_model=Player)
async def get_player_by_name(
    player_name: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
) -> dict:
    player = await player_service.get_player_by_name(player_name, session)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )
    return player

@player_router.get("/{player_uid}", response_model=Player)
async def get_player(
    player_uid: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
) -> dict:
    player = await player_service.get_player(player_uid, session)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )
    return player


@player_router.patch("/{player_uid}", response_model=Player)
async def update_player(
    player_uid: str,
    player_data: PlayerUpdateModel,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
) -> dict:

    updated_player = await player_service.update_player(
        player_uid, player_data, session
    )
    if updated_player:
        return updated_player
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with uid:{player_uid} not found",
        )


@player_router.delete("/{player_uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(
    player_uid: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
):
    result = await player_service.delete_player(player_uid, session)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with uid:{player_uid} not found",
        )
    return

