import asyncio
import click
from db.main import get_session
from auth.service.auth import AuthType
from services.auth import auth_service

@click.group()
def cli():
    """Token generator"""
    pass


@cli.command()
@click.argument('player_uid')
def gen(player_uid: str):
    async def run():
        
        # Simulate session or use a real database session if needed
        async for session in get_session():
            # Ensure the user exists (optional but recommended)
            player = await auth_service.get_player_by_uid(player_uid, session)
            if not player:
                raise ValueError(f"No user found with UUID: {player_uid}")
            
            # Generate tokens
            tokens = auth_service.create_tokens(player_uid, AuthType.STEAM)
            print("Access Token:", tokens.access_token)
            print("Refresh Token:", tokens.refresh_token)
    asyncio.run(run())

if __name__ == "__main__":
    cli()
