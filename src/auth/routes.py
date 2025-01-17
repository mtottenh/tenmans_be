from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from auth.models import Player, PlayerRole, Role
from auth.schemas import (
    PlayerEmailCreate, 
    TokenResponse,
    PlayerUpdate,
    PlayerLogin, 
    RefreshTokenRequest,
    PlayerPublic,
    AuthType,
    # PasswordResetRequest,
    # PasswordResetConfirm,
    # EmailVerificationRequest
)
from auth.service import AuthService
from auth.dependencies import (
    get_session,
    RefreshTokenBearer,
    AccessTokenBearer,
    get_current_player,
    CurrentPlayer
)
from pydantic import BaseModel
from state.service import StateService, StateType, get_state_service
from starlette.responses import RedirectResponse
from typing import Optional, List
import re
from config import Config
from openid.consumer.consumer import Consumer, SUCCESS, FAILURE
from openid.store.memstore import MemoryStore
import logging

from teams.schemas import PlayerRosterHistory
from teams.service import TeamService

LOG =logging.getLogger('uvicorn.error')

auth_router = APIRouter(prefix="/auth")
auth_service = AuthService()

STEAM_OPENID_URL = 'https://steamcommunity.com/openid'
STEAM_ID_RE = re.compile('steamcommunity.com/openid/id/(.*?)$')

@auth_router.post("/login/email")
async def login_with_email(
    login_data: PlayerLogin,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Login with email/password"""
    result = await auth_service.authenticate_player(login_data, session)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    player, tokens = result
    
    # Store tokens in state service
    state_id = await state_service.store_state(
        StateType.AUTH,
        tokens,
        metadata={"player_id": str(player.uid)}
    )
    
    # Return redirect to frontend callback
    return RedirectResponse(
        f"{Config.FRONTEND_URL}/auth/callback?state={state_id}",
        status_code=status.HTTP_303_SEE_OTHER
    )

def get_openid_consumer():
    return Consumer({}, None)

@auth_router.get("/login/steam")
async def login_with_steam(request: Request):
    """Initialize Steam OpenID login flow"""
    # Initialize OpenID consumer
    oidconsumer = get_openid_consumer()
    
    try:
        auth_request = oidconsumer.begin(STEAM_OPENID_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return_url = str(request.base_url) + "api/v1/auth/steam/callback"
    LOG.info(f"client_host: {str(request.client.host)} base_url: {str(request.base_url)}")
    return RedirectResponse(auth_request.redirectURL(
        return_to=return_url,
        realm=str(request.base_url)
    ))
import traceback
@auth_router.get("/steam/callback")
async def steam_callback(
    request: Request,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Handle Steam OpenID callback"""
    LOG.info("Got to callback handler")
    oidconsumer = get_openid_consumer()
    params = dict(request.query_params)
    current_url = str(request.url)
    
    try:
        info = oidconsumer.complete(params, current_url)
        if info.status != SUCCESS:
            raise HTTPException(status_code=400, detail="Steam authentication failed")

        match = STEAM_ID_RE.search(info.identity_url)
        if not match:
            raise HTTPException(status_code=400, detail="Could not extract Steam ID")
        LOG.info(f"Got Auth callback!: {info.identity_url}")
        steam_id = match.group(1)
        LOG.info("Steam ID: {setam_id}")
        player = await auth_service.get_player_by_steam_id(steam_id, session)
        LOG.info("player: {player}")
        if not player:
            LOG.info("Creating new player")
            player = await auth_service.create_steam_player(steam_id, session)
        
        tokens = auth_service.create_tokens(str(player.uid), AuthType.STEAM)
        
        # Store tokens in state service
        state_id = await state_service.store_state(
            StateType.AUTH,
            tokens,
            metadata={"player_id": str(player.uid)}
        )
        return RedirectResponse(
            f"http://localhost:5173/auth/callback?state={state_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
        # TODO = uncomment for deployment         
        # return RedirectResponse(
        #     f"{Config.FRONTEND_URL}/auth/callback?state={state_id}",
        #     status_code=status.HTTP_303_SEE_OTHER
        # )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(traceback.format_exc()))

@auth_router.get("/exchange-state")
async def exchange_state(
    state_id: str,
    state_service: StateService = Depends(get_state_service)
):
    """Exchange state ID for auth tokens"""
    result = await state_service.retrieve_state(StateType.AUTH, state_id, TokenResponse)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state"
        )
    
    tokens, metadata = result
    return tokens

# # Password Reset Flow
# @auth_router.post("/password-reset/request")
# async def request_password_reset(
#     reset_request: PasswordResetRequest,
#     state_service: StateService = Depends(get_state_service),
#     session: AsyncSession = Depends(get_session)
# ):
#     """Request password reset"""
#     player = await auth_service.get_player_by_email(reset_request.email, session)
#     if not player:
#         # Return success even if email not found for security
#         return {"message": "If account exists, reset instructions have been sent"}
    
#     # Generate and store reset token
#     state_id = await state_service.store_state(
#         StateType.PASSWORD_RESET,
#         reset_request,
#         metadata={"player_id": str(player.uid)}
#     )
    
#     # TODO: Send reset email with state_id
#     return {"message": "Reset instructions have been sent"}

# @auth_router.post("/password-reset/confirm")
# async def confirm_password_reset(
#     reset_confirm: PasswordResetConfirm,
#     state_service: StateService = Depends(get_state_service),
#     session: AsyncSession = Depends(get_session)
# ):
#     """Confirm password reset"""
#     result = await state_service.retrieve_state(
#         StateType.PASSWORD_RESET,
#         reset_confirm.token,
#         PasswordResetRequest
#     )
    
#     if not result:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Invalid or expired reset token"
#         )
    
#     reset_request, metadata = result
#     # TODO: Update password
#     return {"message": "Password updated successfully"}

# File Upload Token


@auth_router.post("/register/email")
async def register_with_email(
    player_data: PlayerEmailCreate,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Register a new player with email/password"""
    try:
        player, tokens = await auth_service.create_player(player_data, session)
        
        # Store tokens in state service
        state_id = await state_service.store_state(
            StateType.AUTH,
            tokens,
            metadata={
                "player_id": str(player.uid),
                "registration": True
            }
        )
        
        # Generate email verification token
        verification_state_id = await state_service.store_state(
            StateType.EMAIL_VERIFICATION,
            BaseModel(email=player_data.email),
            metadata={"player_id": str(player.uid)}
        )
        
        # TODO: Send verification email with verification_state_id
        
        # Redirect to frontend with auth state
        return RedirectResponse(
            f"{Config.FRONTEND_URL}/auth/callback?state={state_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# TODO:
# Get a new access token using a refresh token.
# Generic get routes.
access_token_bearer = AccessTokenBearer()

@auth_router.get("/", response_model=List[PlayerPublic])
async def get_players(
    player_details = Depends(access_token_bearer),
    session: AsyncSession = Depends(get_session),
):
    players = await auth_service.get_all_players(session)
    players = [p for p in players if p.name != "SYSTEM" ] # Don't return the system user to external queries
    return players


@auth_router.get("/me", response_model=PlayerPublic)
async def get_current_player_route(player = Depends(get_current_player)):
    return player


@auth_router.get("/name/{player_name}", response_model=PlayerPublic)
async def get_player_by_name(
    player_name: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
) -> dict:
    player = await auth_service.get_player_by_name(player_name, session)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )
    return player

@auth_router.get("/id/{player_uid}", response_model=PlayerPublic)
async def get_player(
    player_uid: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
) -> dict:
    player = await auth_service.get_player_by_uid(player_uid, session)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )
    return player

team_service = TeamService()
@auth_router.get('/id/{player_uid}/teams',response_model=PlayerRosterHistory)
async def get_player_team(
    player_uid: str,
    session: AsyncSession = Depends(get_session),
    _ = Depends(access_token_bearer)
):
    teams = await team_service.get_teams_for_player_by_player_id(player_uid, session)
    return teams

# TODO - Add AuthZ to this endpoint.
@auth_router.patch("/id/{player_uid}", response_model=PlayerPublic)
async def update_player(
    player_uid: str,
    player_data: PlayerUpdate,
    session: AsyncSession = Depends(get_session),
    player_details: Player =Depends(get_current_player),
) -> dict:

    if player_uid != str(player_details.uid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Players can only edit their own profiles {player_uid} != {str(player_details.uid)} "
        )
    updated_player = await auth_service.update_player(
        player_uid, player_data, session
    )
    if updated_player:
        return updated_player
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with uid:{player_uid} not found",
        )


@auth_router.delete("/id/{player_uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(
    player_uid: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(get_current_player),
):
    result = await auth_service.delete_player(player_uid, session)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with uid:{player_uid} not found",
        )
    return

REFRESH_TOKEN_EXPIRY = 2

refresh_token_bearer = RefreshTokenBearer()

# @auth_router.post("/refresh")
# async def get_new_access_token(token_details: dict = Depends(refresh_token_bearer), session: AsyncSession  = Depends(get_session)):
#     expiry_date = token_details["exp"]
#     if datetime.fromtimestamp(expiry_date) > datetime.now():
#         player = await auth_service.player_exists_by_id(token_details['player']['player_uid'], session)
#         if not player:
#             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Refresh Token")
#         new_access_token = auth_service.create_token(player_data=token_details["player"])
#         return JSONResponse(content={"access_token": new_access_token})
#     raise HTTPException(
#         status_code=status.HTTP_400_BAD_REQUEST,
#         detail="Invalid or expired refresh token",
#     )

