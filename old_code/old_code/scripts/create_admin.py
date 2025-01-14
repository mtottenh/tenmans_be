import argparse
import asyncio

from src.players.models import Player, PlayerRoles
from src.db.main import engine
from src.players.service import PlayerService
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
player_service = PlayerService()

Session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
async def mark_player_as_admin(session, player_name) -> Player | None:

    player: Player = await player_service.get_player_by_name( player_name, session)
    if player is None:
        print(f"Error, no player named '{player_name}'")
    player.role = PlayerRoles.ADMIN
    session.add(player)
    await session.commit()
    await session.refresh(player)
    return player

async def print_all_players(session):
    current_players = await player_service.get_all_players(session)
    admins = [p for p in current_players if p.role == 'admin' ]
    users = [ p for p in current_players if p.role == 'user']
    if len(admins) > 0:
        print ("Current Administrators: ")
        for p in admins:
            print(f" * {p.name}: {str(p.role).upper()}")
    if len(users) > 0:
        print ("Current users: ")
        for p in users:
            print(f" * {p.name}: {str(p.role).upper()}")

async def main(args):
    async with Session() as session:
        if args.list_players:
            await print_all_players(session)
        if args.make_admin:
            await mark_player_as_admin(session, args.make_admin)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                    prog='Add Admin',
                    description='Modifies a current user in the DB to be a league admin',
                    epilog='Useful for the initial Admin add')
    parser.add_argument('--list-players',action='store_true')
    parser.add_argument('--make-admin', action='store', type=str)
    args = parser.parse_args()
    asyncio.run(main(args))
        
