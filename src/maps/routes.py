import os
import aiofiles
from fastapi import APIRouter, Depends, Form, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.exceptions import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from src.players.dependencies import RoleChecker
from src.db.main import get_session
from .models import Map
from .schema import MapCreateModel, MapRespModel
from .service import MapService
from typing import List

admin_checker = Depends(RoleChecker(["admin", "user"]))
map_router = APIRouter(prefix="/maps")
map_service = MapService()


@map_router.post("/", dependencies=[admin_checker], status_code=status.HTTP_201_CREATED)
async def create_team(
    img: UploadFile,
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    map_exists = await map_service.map_exists(name, session)
    if map_exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Map with name '{name}' already exists",
        )
    new_map = await map_service.create_map(MapCreateModel(name=name), session)
    filedir = os.path.join(os.getcwd(), 'map_store', str(new_map.id))
    if not os.path.exists(filedir):
        os.makedirs(filedir)
    server_filename = f"{filedir}/{img.filename}"
    async with aiofiles.open(server_filename, 'wb') as out_file:
        while content := await img.read(1024):
            await out_file.write(content)
    new_map.img = server_filename
    session.add(new_map)
    await session.commit()
    await session.refresh(new_map)
    return new_map


async def get_map_img(map: Map):
    if os.path.exists(map.img):
        return FileResponse(map.img)


@map_router.get('/', response_model=List[MapRespModel])
async def get_all_maps(
    session: AsyncSession = Depends(get_session),
):
    db_maps = await map_service.get_all_maps(session)

    maps = [MapRespModel(name=m.name, id=str(m.id), img=map_service.get_map_img_path(m)) for m in db_maps]
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
