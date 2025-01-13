# permissions/cli.py

import asyncio
import logging
from pathlib import Path
from typing import Optional
import click
from sqlmodel.ext.asyncio.session import AsyncSession

from db.main import get_session
from .manager import PermissionManager
from .auditor import PermissionAuditor
from .reporter import PermissionReporter
from .ui import PermissionUI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_db_session() -> AsyncSession:
    """Get database session"""
    session_gen = get_session()
    session = await session_gen.__anext__()
    return session

@click.group()
def cli():
    """Permission management utility"""
    pass

@cli.command()
@click.argument('steam_id')
@click.option('--email', help='Optional email for admin user')
def create_admin(steam_id: str, email: Optional[str]):
    """Create initial admin user"""
    async def run():
        async with await get_db_session() as session:
            manager = PermissionManager(session)
            try:
                player = await manager.create_initial_admin(steam_id, email)
                click.echo(f"Created admin user with UID: {player.uid}")
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)

    asyncio.run(run())

@cli.command()
@click.argument('player_uid')
def edit(player_uid: str):
    """Edit user permissions interactively"""
    async def run():
        async with await get_db_session() as session:
            ui = PermissionUI(session)
            await ui.edit_permissions(player_uid)

    asyncio.run(run())

@cli.command()
@click.option('--player', help='Audit specific player by UID')
@click.option(
    '--format',
    type=click.Choice(['csv', 'json', 'text']),
    default='text',
    help='Output format'
)
@click.option('--output', help='Output file path')
def audit(player: Optional[str], format: str, output: Optional[str]):
    """Audit user permissions"""
    async def run():
        async with await get_db_session() as session:
            auditor = PermissionAuditor(session)
            
            try:
                if player:
                    results = [await auditor.audit_player(player)]
                else:
                    results = await auditor.audit_all_players()
                    
                # Generate report
                if format == 'csv':
                    PermissionReporter.generate_csv_report(
                        results,
                        Path(output or 'permission_audit.csv')
                    )
                elif format == 'json':
                    PermissionReporter.generate_json_report(
                        results,
                        Path(output or 'permission_audit.json')
                    )
                else:
                    summary = PermissionReporter.generate_summary_report(results)
                    click.echo(summary)
                    
            except Exception as e:
                logger.error(f"Error during permission audit: {e}", exc_info=True)
                raise click.ClickException(str(e))

    asyncio.run(run())

@cli.command()
def roles():
    """Manage roles interactively"""
    async def run():
        async with await get_db_session() as session:
            ui = PermissionUI(session)
            await ui.manage_roles()

    asyncio.run(run())

if __name__ == '__main__':
    cli()