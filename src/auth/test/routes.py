from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from auth.models import AuthType
from auth.schemas import PlayerEmailCreate, PlayerLogin, TokenResponse
from auth.service import AuthService
from db.main import get_session
from state.service import StateService, StateType
from config import Config

auth_test_router = APIRouter(prefix="/auth/test")
auth_service = AuthService()
state_service = StateService(Config.REDIS_URL)

@auth_test_router.post("/register", response_model=TokenResponse)
async def register_test_user(
    user_data: PlayerEmailCreate,
    session: AsyncSession = Depends(get_session)
):
    """Register a test user with email/password"""
    try:
        player, tokens = await auth_service.create_player(user_data, session)
        state_id = await state_service.store_state(
            StateType.AUTH,
            tokens,
            metadata={"player_id": str(player.uid)}
        )
        return RedirectResponse(
            f"http://localhost:5173/auth/callback?state={state_id}",
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
            metadata={"player_id": str(player.uid)}
        )
        return RedirectResponse(
            f"http://localhost:5173/auth/callback?state={state_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
            )
