from sqlmodel.ext.asyncio.session import AsyncSession
from .schemas import PlayerCreateModel, PlayerUpdateModel
from sqlmodel import select, desc
from .models import Player
from .utils import generate_password_hash


class PlayerService:
    async def get_all_players(self, session: AsyncSession):
        stmnt = select(Player).order_by(desc(Player.created_at))

        result = await session.exec(stmnt)

        return result.all()

    async def get_player(self, player_uid: str, session: AsyncSession):
        stmnt = select(Player).where(Player.uid == player_uid)

        result = await session.exec(stmnt)

        return result.first()

    async def get_player_by_email(self, email: str, session: AsyncSession):
        stmnt = select(Player).where(Player.email == email)
        result = await session.exec(stmnt)

        return result.first()


    async def get_player_by_name(self, name: str, session: AsyncSession):
        stmnt = select(Player).where(Player.name == name)
        result = await session.exec(stmnt)

        return result.first()

    async def player_exists(self, email: str, session: AsyncSession) -> bool:
        player = await self.get_player_by_email(email, session)
        if player:
            return True
        else:
            return False

    async def create_player(
        self, player_data: PlayerCreateModel, session: AsyncSession
    ):
        player_data_dict = player_data.model_dump()
        new_player = Player(**player_data_dict)
        new_player.password_hash = generate_password_hash(player_data_dict["password"])
        new_player.role = 'user'
        session.add(new_player)

        await session.commit()

        return new_player

    async def update_player(
        self, player_uid: str, player_data: PlayerUpdateModel, session: AsyncSession
    ):
        player_to_update = await self.get_player(player_uid, session)
        if player_to_update is not None:
            update_data = player_data.model_dump()
            for k, v in update_data.items():
                setattr(player_to_update, k, v)

            await session.commit()
        return player_to_update

    async def delete_player(self, player_uid: str, session: AsyncSession):
        player_to_delete = await self.get_player(player_uid, session)

        if player_to_delete is not None:
            await session.delete(player_to_delete)
            await session.commit()
            return {}
        else:
            return None
