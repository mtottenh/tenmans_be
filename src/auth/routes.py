from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from auth.models import Player
from auth.schemas import (
    PlayerWithTeamBasic,
    RefreshTokenRequest, 
    TokenResponse,
    PlayerUpdate,
    PlayerPublic,
    AuthType,
)
from auth.dependencies import (
    get_session,
    RefreshTokenBearer,
    AccessTokenBearer,
    get_current_player,
)


from competitions.models.seasons import Season
from competitions.season.dependencies import get_active_season
from state.service import StateService, StateType, get_state_service
from starlette.responses import RedirectResponse
from typing import List
import re
from openid.consumer.consumer import Consumer, SUCCESS
import logging
from services.team import team_service
from services.auth import auth_service
from teams.schemas import PlayerRosterHistory
from config import Config

LOG =logging.getLogger('uvicorn.error')
auth_router = APIRouter(prefix="/auth")

STEAM_OPENID_URL = 'https://steamcommunity.com/openid'
STEAM_ID_RE = re.compile('steamcommunity.com/openid/id/(.*?)$')

def get_openid_consumer():
    return Consumer({}, None)

@auth_router.get("/login/steam")
async def login_with_steam(request: Request, session: AsyncSession = Depends(get_session)):
    """Initialize Steam OpenID login flow"""
    system_user = await auth_service.get_player_by_name("SYSTEM", session)
    if not system_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to register/login players. SYSTEM user not yet created"
        )
    # Initialize OpenID consumer
    oidconsumer = get_openid_consumer()
    
    try:
        auth_request = oidconsumer.begin(STEAM_OPENID_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return_url = str(request.base_url.replace(scheme='https')) + "api/v1/auth/steam/callback"
    LOG.info(f"client_host: {str(request.client.host)} base_url: {str(request.base_url)}")
    return RedirectResponse(auth_request.redirectURL(
        return_to=return_url,
        realm=str(request.base_url.replace(scheme='https'))
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
    current_url = str(request.url.replace(scheme='https'))
    
    try:
        LOG.info(f"Params {params} current URL: {current_url}")
        info = oidconsumer.complete(params, current_url)
        if info.status != SUCCESS:
            raise HTTPException(status_code=400, detail="Steam authentication failed")

        match = STEAM_ID_RE.search(info.identity_url)
        if not match:
            raise HTTPException(status_code=400, detail="Could not extract Steam ID")
        LOG.info(f"Got Auth callback!: {info.identity_url}")
        steam_id = match.group(1)
        LOG.info(f"Steam ID: {steam_id}")
        player = await auth_service.get_player_by_steam_id(steam_id, session)
        LOG.info(f"player: {player}")
        tokens = None
        if not player:
            LOG.info("Creating new player")
            system_user = await auth_service.get_player_by_name("SYSTEM", session)
            player = await auth_service.create_steam_player(steam_id, actor=system_user, session=session)

        tokens = auth_service.create_auth_tokens(player.id, player.auth_type)
        # Store tokens in state service
        state_id = await state_service.store_state(
            StateType.AUTH,
            tokens,
            metadata={"player_id": str(player.id)}
        )
        redir_url=f"{Config.FRONTEND_URL}auth/callback?state={state_id}"
        LOG.info(f"Redirecting to: {redir_url}")
        # TODO = uncomment for deployment         
        return RedirectResponse(
            redir_url,
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except Exception as e:
        raise # HTTPException(status_code=400, detail=str(e))

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

# TODO - Probably need to make the frontend not use this
# endpoint for the player search dialog.
@auth_router.get("/current-season", response_model=List[PlayerWithTeamBasic])
async def get_players(
    player_details = Depends(access_token_bearer),
    session: AsyncSession = Depends(get_session),
    season: Season = Depends(get_active_season)

):
    if season is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No active season")
    players = await auth_service.get_all_players_with_basic_team_info(season.id, session)
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

@auth_router.get("/id/{player_id}", response_model=PlayerPublic)
async def get_player(
    player_id: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(access_token_bearer),
) -> dict:
    player = await auth_service.get_player_by_id(player_id, session)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )
    return player


@auth_router.get('/id/{player_id}/teams',response_model=PlayerRosterHistory)
async def get_player_team(
    player_id: str,
    session: AsyncSession = Depends(get_session),
    _ = Depends(access_token_bearer)
):
    teams = await team_service.get_teams_for_player_by_player_id(player_id, session)
    return teams

# TODO - Add AuthZ to this endpoint.
@auth_router.patch("/id/{player_id}", response_model=PlayerPublic)
async def update_player(
    player_id: str,
    player_data: PlayerUpdate,
    session: AsyncSession = Depends(get_session),
    player_details: Player =Depends(get_current_player),
) -> dict:

    if player_id != str(player_details.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Players can only edit their own profiles {player_id} != {str(player_details.id)} "
        )
    
    updated_player = await auth_service.update_player(
        player_details, player_data, actor=player_details, session=session
    )
    if updated_player:
        return updated_player
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with id:{player_id} not found",
        )


@auth_router.delete("/id/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(
    player_id: str,
    session: AsyncSession = Depends(get_session),
    player_details=Depends(get_current_player),
):
    result = await auth_service.soft_delete_player(player_id, session)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with id:{player_id} not found",
        )
    return

REFRESH_TOKEN_EXPIRY = 2

refresh_token_bearer = RefreshTokenBearer()

@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    token_data: RefreshTokenRequest,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Get new access token using refresh token"""
    # Verify refresh token
    token_payload = auth_service.verify_token(token_data.refresh_token)
    if not token_payload or not token_payload.get('is_refresh'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    # Get player
    player = await auth_service.get_player_by_id(token_payload['player_id'], session)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Player not found"
        )
    
    # Create new tokens
    tokens = auth_service.create_auth_tokens(
        str(player.id), 
        AuthType(token_payload['auth_type'])
    )
    
    # Store tokens in state service
    state_id = await state_service.store_state(
        StateType.AUTH,
        tokens,
        metadata={"player_id": str(player.id)}
    )
    # Return redirect to frontend callback
    return RedirectResponse(
        f"{Config.FRONTEND_URL}/auth/callback?state={state_id}",
        status_code=status.HTTP_303_SEE_OTHER
    )