from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from src.auth.schemas import (
    PlayerEmailCreate, 
    TokenResponse,
    PlayerLogin, 
    RefreshTokenRequest,
    PlayerPublic,
    AuthType,
    PasswordResetRequest,
    PasswordResetConfirm,
    EmailVerificationRequest
)
from src.auth.service import AuthService
from src.auth.dependencies import (
    get_session,
    RefreshTokenBearer,
    get_current_player
)
from src.state.service import StateService, StateType, get_state_service
from starlette.responses import RedirectResponse
from typing import Optional
import re

auth_router = APIRouter(prefix="/auth")
auth_service = AuthService()

STEAM_OPENID_URL = 'https://steamcommunity.com/openid'
STEAM_ID_RE = re.compile('steamcommunity.com/openid/id/(.*?)

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

@auth_router.get("/login/steam")
async def login_with_steam(request: Request):
    """Initialize Steam OpenID login flow"""
    # Initialize OpenID consumer
    oidconsumer = consumer.Consumer({}, None)
    
    try:
        auth_request = await oidconsumer.begin(STEAM_OPENID_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return_url = str(request.base_url) + "auth/steam/callback"
    
    return RedirectResponse(auth_request.redirectURL(
        return_to=return_url,
        trust_root=str(request.base_url)
    ))

@auth_router.get("/steam/callback")
async def steam_callback(
    request: Request,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Handle Steam OpenID callback"""
    oidconsumer = consumer.Consumer({}, None)
    params = dict(request.query_params)
    current_url = str(request.url)
    
    try:
        info = await oidconsumer.complete(params, current_url)
        if info.status != consumer.SUCCESS:
            raise HTTPException(status_code=400, detail="Steam authentication failed")

        match = STEAM_ID_RE.search(info.identity_url)
        if not match:
            raise HTTPException(status_code=400, detail="Could not extract Steam ID")
        
        steam_id = match.group(1)
        player = await auth_service.get_player_by_steam_id(steam_id, session)
        
        if not player:
            player = await auth_service.create_steam_player(steam_id, session)
        
        tokens = auth_service.create_tokens(str(player.uid), AuthType.STEAM)
        
        # Store tokens in state service
        state_id = await state_service.store_state(
            StateType.AUTH,
            tokens,
            metadata={"player_id": str(player.uid)}
        )
        
        return RedirectResponse(
            f"{Config.FRONTEND_URL}/auth/callback?state={state_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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

# Password Reset Flow
@auth_router.post("/password-reset/request")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Request password reset"""
    player = await auth_service.get_player_by_email(reset_request.email, session)
    if not player:
        # Return success even if email not found for security
        return {"message": "If account exists, reset instructions have been sent"}
    
    # Generate and store reset token
    state_id = await state_service.store_state(
        StateType.PASSWORD_RESET,
        reset_request,
        metadata={"player_id": str(player.uid)}
    )
    
    # TODO: Send reset email with state_id
    return {"message": "Reset instructions have been sent"}

@auth_router.post("/password-reset/confirm")
async def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Confirm password reset"""
    result = await state_service.retrieve_state(
        StateType.PASSWORD_RESET,
        reset_confirm.token,
        PasswordResetRequest
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    reset_request, metadata = result
    # TODO: Update password
    return {"message": "Password updated successfully"}

# File Upload Token
@auth_router.post("/upload-token")
async def create_upload_token(
    current_player = Depends(get_current_player),
    state_service: StateService = Depends(get_state_service)
):
    """Create temporary file upload token"""
    upload_data = {"player_id": str(current_player.uid)}
    state_id = await state_service.store_state(
        StateType.FILE_UPLOAD,
        BaseModel(**upload_data)
    )
    
    return {"upload_token": state_id}
)

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

@auth_router.get("/login/steam")
async def login_with_steam(request: Request):
    """Initialize Steam OpenID login flow"""
    # Initialize OpenID consumer
    oidconsumer = consumer.Consumer({}, None)
    
    try:
        auth_request = await oidconsumer.begin(STEAM_OPENID_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return_url = str(request.base_url) + "auth/steam/callback"
    
    return RedirectResponse(auth_request.redirectURL(
        return_to=return_url,
        trust_root=str(request.base_url)
    ))

@auth_router.get("/steam/callback")
async def steam_callback(
    request: Request,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Handle Steam OpenID callback"""
    oidconsumer = consumer.Consumer({}, None)
    params = dict(request.query_params)
    current_url = str(request.url)
    
    try:
        info = await oidconsumer.complete(params, current_url)
        if info.status != consumer.SUCCESS:
            raise HTTPException(status_code=400, detail="Steam authentication failed")

        match = STEAM_ID_RE.search(info.identity_url)
        if not match:
            raise HTTPException(status_code=400, detail="Could not extract Steam ID")
        
        steam_id = match.group(1)
        player = await auth_service.get_player_by_steam_id(steam_id, session)
        
        if not player:
            player = await auth_service.create_steam_player(steam_id, session)
        
        tokens = auth_service.create_tokens(str(player.uid), AuthType.STEAM)
        
        # Store tokens in state service
        state_id = await state_service.store_state(
            StateType.AUTH,
            tokens,
            metadata={"player_id": str(player.uid)}
        )
        
        return RedirectResponse(
            f"{Config.FRONTEND_URL}/auth/callback?state={state_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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

# Password Reset Flow
@auth_router.post("/password-reset/request")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Request password reset"""
    player = await auth_service.get_player_by_email(reset_request.email, session)
    if not player:
        # Return success even if email not found for security
        return {"message": "If account exists, reset instructions have been sent"}
    
    # Generate and store reset token
    state_id = await state_service.store_state(
        StateType.PASSWORD_RESET,
        reset_request,
        metadata={"player_id": str(player.uid)}
    )
    
    # TODO: Send reset email with state_id
    return {"message": "Reset instructions have been sent"}

@auth_router.post("/password-reset/confirm")
async def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    state_service: StateService = Depends(get_state_service),
    session: AsyncSession = Depends(get_session)
):
    """Confirm password reset"""
    result = await state_service.retrieve_state(
        StateType.PASSWORD_RESET,
        reset_confirm.token,
        PasswordResetRequest
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    reset_request, metadata = result
    # TODO: Update password
    return {"message": "Password updated successfully"}

# File Upload Token
@auth_router.post("/upload-token")
async def create_upload_token(
    current_player = Depends(get_current_player),
    state_service: StateService = Depends(get_state_service)
):
    """Create temporary file upload token"""
    upload_data = {"player_id": str(current_player.uid)}
    state_id = await state_service.store_state(
        StateType.FILE_UPLOAD,
        BaseModel(**upload_data)
    )
    
    return {"upload_token": state_id}
