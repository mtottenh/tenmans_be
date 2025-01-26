from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from auth.schemas import PlayerEmailCreate, PlayerLogin, TokenResponse
from db.main import get_session
from state.service import StateType
from services.auth import auth_service
from services.state import state_service
from config import Config

auth_test_router = APIRouter(prefix="/auth/test")


@auth_test_router.post("/register", response_model=TokenResponse)
async def register_test_user(
    user_data: PlayerEmailCreate,
    session: AsyncSession = Depends(get_session)
):
    """Register a test user with email/password"""
    try:
        system_user = await auth_service.get_player_by_name("SYSTEM", session)
        if not system_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to register new players. SYSTEM user not yet created"
            )
        player = await auth_service.create_player(user_data, actor=system_user, session=session)
        tokens = auth_service.create_auth_tokens(player.id, player.auth_type)
        state_id = await state_service.store_state(
            StateType.AUTH,
            tokens,
            metadata={"player_id": str(player.id)}
        )
        return RedirectResponse(
            f"{Config.FRONTEND_URL}auth/callback?state={state_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@auth_test_router.post("/login/email", response_model=TokenResponse) 
async def login_test_user(
    login_data: PlayerLogin,
    session: AsyncSession = Depends(get_session)
):
    """Login with email/password"""

    result = await auth_service.authenticate_player(login_data, session)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    try:
        player, tokens = result
        state_id = await state_service.store_state(
            StateType.AUTH,
            tokens,
            metadata={"player_id": str(player.id)}
        )
        return RedirectResponse(
            f"{Config.FRONTEND_URL}auth/callback?state={state_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
            )
