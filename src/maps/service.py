from .schemas import MapCreate
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from typing import Sequence
from .models import Map


class MapNotFoundException(Exception):
    pass


class MapService:
    async def get_all_maps(self, session: AsyncSession) -> Sequence[Map]:
        stmnt = select(Map).order_by(desc(Map.name))
        return (await session.execute(stmnt)).all()

    async def get_map(self, id: str, session: AsyncSession) -> Map:
        stmnt = select(Map).where(Map.id == id)
        map = (await session.execute(stmnt)).first()
        if map is None:
            raise MapNotFoundException(f"Map id={id} not found")
        return map

    async def get_map_by_name(self, name: str, session: AsyncSession) -> Map:
        stmnt = select(Map).where(Map.name == name)
        map = (await session.execute(stmnt)).first()
        if map is None:
            raise MapNotFoundException(f"Map {name} not found")
        return map

    async def create_map(self, map: MapCreate, session: AsyncSession) -> Map:
        map_data_dict = map.model_dump()
        new_map = Map(**map_data_dict)
        session.add(new_map)
        await session.commit()
        await session.refresh(new_map)
        return new_map

    async def map_exists(self, name: str, session: AsyncSession) -> bool:
        try:
            _ = await self.get_map_by_name(name, session)
            return True
        except MapNotFoundException:
            return False

    def get_map_img_path(self, m: Map) -> str:
        return f"/maps/id/{m.id}/img"
