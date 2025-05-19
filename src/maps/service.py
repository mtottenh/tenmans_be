from collections.abc import Sequence
from datetime import datetime, timezone

from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from competitions.base_schemas import GameMode, MapCategory

from .models import Map
from .schemas import MapCreate


class MapNotFoundError(Exception):
    pass


# TODO - Add Aduit module integration
class MapService:
    async def get_all_maps(self, session: AsyncSession) -> Sequence[Map]:
        stmnt = select(Map).order_by(desc(Map.name))
        return ((await session.execute(stmnt)).scalars()).all()

    async def get_map(self, id: str, session: AsyncSession) -> Map:
        stmnt = select(Map).where(Map.id == id)
        map = ((await session.execute(stmnt)).scalars()).first()
        if map is None:
            raise MapNotFoundError(f"Map id={id} not found")
        return map

    async def get_map_by_name(self, name: str, session: AsyncSession) -> Map:
        stmnt = select(Map).where(Map.name == name)
        map = ((await session.execute(stmnt)).scalars()).first()
        if map is None:
            raise MapNotFoundError(f"Map {name} not found")
        return map

    async def get_maps_by_mode(
        self, game_mode: GameMode, session: AsyncSession
    ) -> list[Map]:
        """Get all maps that support a specific game mode"""
        stmt = (
            select(Map)
            .where(Map.supported_modes.contains([game_mode]))
            .order_by(Map.name)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_maps_by_category(
        self, category: MapCategory, session: AsyncSession
    ) -> list[Map]:
        """Get all maps in a specific category"""
        stmt = select(Map).where(Map.category == category).order_by(Map.name)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def create_map(self, map: MapCreate, session: AsyncSession) -> Map:
        new_map = Map(
            name=map.name,
            img=map.img,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(new_map)
        await session.commit()
        await session.refresh(new_map)
        return new_map

    async def map_exists(self, name: str, session: AsyncSession) -> bool:
        try:
            _ = await self.get_map_by_name(name, session)
            return True
        except MapNotFoundError:
            return False

    def get_map_img_path(self, m: Map) -> str:
        return f"/maps/id/{m.id}/img"


def create_map_service() -> MapService:
    return MapService()

