from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from src.db.main import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from src.players.service import PlayerService
from src.players.models import Player
from src.players.schemas import PlayerUpdateModel, PlayerCreateModel

from typing import List


player_router = APIRouter()
player_service = PlayerService()

@player_router.get('/', response_model=List[Player])
async def get_players(session: AsyncSession = Depends(get_session) ):
    players = await player_service.get_all_players(session)
    return players

@player_router.post('/', status_code=status.HTTP_201_CREATED, response_model=Player)
async def create_player(player_data: PlayerCreateModel, session: AsyncSession = Depends(get_session) ) -> dict:
    new_player = await player_service.create_player(player_data, session)
    return new_player

@player_router.get('/{player_uid}', response_model=Player)
async def get_player(player_uid: str, session: AsyncSession = Depends(get_session) ) -> dict:
    player = await player_service.get_player(player_uid, session)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    return player

@player_router.patch('/{player_uid}', response_model=Player)
async def update_player(
     player_uid: str,
     player_data: PlayerUpdateModel,
     session: AsyncSession = Depends(get_session)
) -> dict:
    
    updated_player = await player_service.update_player(player_uid, player_data, session)
    if updated_player:
        return updated_player
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Player with uid:{player_uid} not found")


@player_router.delete('/{player_uid}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(player_uid: str, session:  AsyncSession = Depends(get_session)):
    result = await player_service.delete_player(
        player_uid, session
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Player with uid:{player_uid} not found")
    return