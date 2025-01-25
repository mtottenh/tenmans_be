import os
from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from fastapi.exceptions import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from auth.dependencies import get_current_player, require_map_management
from auth.models import Player
from db.main import get_session
from .models import Map
from .schemas import MapBase, MapCreate, MapCreateRequest
from typing import List
from services.map import map_service
from services.upload import upload_service


map_router = APIRouter(prefix="/maps")

@map_router.post("/", 
                 dependencies=[Depends(require_map_management)], 
                 status_code=status.HTTP_201_CREATED,
                 response_model=MapBase
                 )
async def create_map(
    map_create_model: MapCreateRequest,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    name = map_create_model.name
    token_id = map_create_model.map_img_token_id
    map_exists = await map_service.map_exists(name, session)
    if map_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Map with name '{name}' already exists",
        )
    # Handle upload result for Map service
    upload_result = await upload_service.get_upload_result(token_id)
    if not upload_result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or expired map upload token",
        )
    final_path = await upload_service.move_upload_if_temp(upload_result, name)
    
    new_map = await map_service.create_map(MapCreate(name=name, img=final_path), session)
    return new_map


async def get_map_img(map: Map):
    if os.path.exists(map.img):
        return FileResponse(map.img)


@map_router.get('/', response_model=List[MapBase])
async def get_all_maps(
    session: AsyncSession = Depends(get_session),
):
    db_maps = await map_service.get_all_maps(session)

    maps = [MapBase(name=m.name, id=str(m.id), img=map_service.get_map_img_path(m)) for m in db_maps]
    return maps


@map_router.get('/id/{id}/img')
async def get_map_by_id(
    id: str,
    session: AsyncSession = Depends(get_session),
):
    map = await map_service.get_map(id, session)
    if map is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Map with id '{id}' not found",
        )
    return await get_map_img(map)


@map_router.get('/name/{name}/img')
async def get_map_by_name(
    name: str,
    session: AsyncSession = Depends(get_session),
):
    map = await map_service.get_map_by_name(name, session)
    if map is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Map with name '{name}' not found",
        )
    return await get_map_img(map)
