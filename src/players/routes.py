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
from bs4 import BeautifulSoup
import httpx
from typing import List
from .utils import create_access_token, decode_token, verify_password
from zenrows import ZenRowsClient
from src.config import Config
zclient = ZenRowsClient(Config.ZENROWS_API_KEY)
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
async def get_new_access_token(token_details: dict = Depends(refresh_token_bearer)):
    expiry_date = token_details["exp"]
    if datetime.fromtimestamp(expiry_date) > datetime.now():
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


@player_router.get("/steam_rank/{player_id}")
async def get_player_rank(player_id: str):
    url = f"https://csstats.gg/player/{player_id}"

    try:
        # Fetch the page HTML
        #async with httpx.AsyncClient() as client:
    #         headers={
    #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    #     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    #     "Accept-Language": "en-US,en;q=0.5",
    #     "Accept-Encoding": "gzip, deflate",
    #     "Connection": "keep-alive",
    #     "Upgrade-Insecure-Requests": "1",
    #     "Sec-Fetch-Dest": "document",
    #     "Sec-Fetch-Mode": "navigate",
    #     "Sec-Fetch-Site": "none",
    #     "Sec-Fetch-User": "?1",
    #     "Cache-Control": "max-age=0",
    # }
    #         response = await client.get(url,headers=headers, follow_redirects=True)
    #         print(response.text)
    #         response.raise_for_status()

        params = {"premium_proxy":"true"}

        response = zclient.get(url, params=params)
        # Parse HTML with BeautifulSoup
        print (response.text)
        soup = BeautifulSoup(response.text, "html.parser")

        # Scrape the best Premier rank (update this selector based on the actual HTML structure)
        # Example: Assuming the rank is in an element like <div class="rank">Premier Rank: Gold</div>
        rank_elements = soup.select("div.rank > .cs2rating, div.best > .cs2rating")  # Adjust selector as per the actual HTML structure

        if rank_elements:
            print(f"RANK: {rank_elements}")
            ranks = []
            for rank_element in rank_elements:
                ranks.append(rank_element.get_text(strip=True).replace(',',''))
            ranks = sorted(ranks,key=int)
            best_rank = ranks[1] if len(ranks) == 2 else ranks[0]
            return {"player_id": player_id, "current_rank": ranks[0], "best_rank": best_rank}
        else:
            raise HTTPException(status_code=404, detail="Rank information not found")

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to retrieve player data {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred while fetching player data {e}")




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

