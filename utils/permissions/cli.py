#!/usr/bin/env python3

import asyncio
import click
import logging
from pathlib import Path
from typing import Optional
import click
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src'))
from db.main import get_session
from manager import PermissionManager
from auditor import PermissionAuditor
from reporter import PermissionReporter
from ui import PermissionUI
from auth.schemas import PermissionTemplate
from sys_user import ensure_system_user
from services.auth import auth_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        async for session in get_session():
            try:
                system_user = await ensure_system_user(session)
                manager = PermissionManager(session, system_user)
            
                player = await manager.create_initial_admin(steam_id, email)
                click.echo(f"Created admin user with UID: {player.id}")
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
                # click.echo(f"Error: {e}", err=True)
                # raise click.ClickException(str(e))

    asyncio.run(run())

@cli.command()
@click.argument('player_id')
def edit(player_id: str):
    """Edit user permissions interactively"""
    async def run():
        async for session in get_session():
            system_user = await ensure_system_user(session)
            ui = PermissionUI(system_user, session)
            await ui.edit_permissions(player_id)
            await session.commit()


    asyncio.run(run())

@cli.command()
@click.option('--player', help='Audit specific player by UID')
@click.option('--format',
    type=click.Choice(['csv', 'json', 'text']),
    default='text',
    help='Output format'
)
@click.option('--output', help='Output file path')
def audit(player: Optional[str], format: str, output: Optional[str]):
    """Audit user permissions"""
    async def run():
        async for session in get_session():
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

@cli.group()
def roles():
    """Role management commands"""
    pass

@roles.command('list')
def list_roles():
    """List all roles and their permissions"""
    async def run():
        async for session in get_session():
            try:
                roles = await auth_service.get_all_roles(session)
                
                if not roles:
                    click.echo("No roles defined")
                    return
                    
                for role in roles:
                    click.echo(f"\nRole: {role.name}")
                    click.echo("Permissions:")
                    for perm in await role.awaitable_attrs.permissions:
                        click.echo(f"  - {perm.name}: {perm.description}")
            except Exception as e:
                raise click.ClickException(str(e))
                    
    asyncio.run(run())

@roles.command('create')
@click.argument('name')
@click.option('--permissions', help='Comma-separated list of permission names')
@click.option('--template', help='Name of template to use for permissions')
def create_role(name: str, permissions: Optional[str], template: Optional[str]):
    """Create a new role"""
    async def run():
        async for session in get_session():
            try:
                system_user = await ensure_system_user(session)
                
                # Get permissions list
                permission_ids = []
                
                if template:
                    # Use template
                    try:
                        template_data = PermissionTemplate.get_template(template)
                        perm_names = template_data["permissions"]
                    except ValueError as e:
                        raise click.ClickException(str(e))
                elif permissions:
                    # Use provided permissions
                    perm_names = [p.strip() for p in permissions.split(",")]
                else:
                    raise click.ClickException("Must specify either --permissions or --template")
                
                # Get permission IDs
                for perm_name in perm_names:
                    perm = await auth_service.get_permission_by_name(perm_name, session)
                    if not perm:
                        raise click.ClickException(f"Permission '{perm_name}' not found")
                    permission_ids.append(perm.id)
                
                
                role = await auth_service.create_role(name, permission_ids, actor=system_user, session=session)
                click.echo(f"Created role '{role.name}' with {len(role.permissions)} permissions")
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise click.ClickException(str(e))
                
    asyncio.run(run())

@roles.command('delete')
@click.argument('name')
@click.option('--force/--no-force', default=False, help='Force deletion even if role is in use')
def delete_role(name: str, force: bool):
    """Delete a role"""
    async def run():
        async for session in get_session():
            try:
                system_user = await ensure_system_user(session)
                role = await auth_service.get_role_by_name(name, session)
                if not role:
                    raise click.ClickException(f"Role '{name}' not found")
                    
                if not force and role.players:
                    click.echo(f"Role '{name}' is assigned to {len(role.players)} players.")
                    click.echo("Use --force to delete anyway")
                    return
                    

                await auth_service.delete_role(role.id, actor=system_user, session=session)
                click.echo(f"Deleted role '{name}'")
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise click.ClickException(str(e))

    asyncio.run(run())



@cli.command('init')
def initialize_permissions():
    """Initialize default roles and permissions from templates"""
    async def run():
        session_gen = get_session()
        async for session in session_gen:
            # try:
                system_user = await ensure_system_user(session)
                
                # Create permissions from all templates
                permissions_created = 0
                all_permissions = set()
                for template in PermissionTemplate.TEMPLATES.values():
                    all_permissions.update(template["permissions"])
                
                for perm_name in sorted(all_permissions):
                    try:
                        if not await auth_service.get_permission_by_name(perm_name, session):
                            await auth_service.create_permission(
                                name=perm_name,
                                description=f"Permission to {perm_name.replace('_', ' ')}",
                                actor=system_user,
                                session=session
                            )
                            permissions_created += 1
                    except Exception as e:
                        click.echo(f"Error creating permission '{perm_name}': {e}")
                        raise
                
                click.echo(f"Created {permissions_created} permissions")
                
                # Create roles from templates
                roles_created = 0
                for template_name, template in PermissionTemplate.TEMPLATES.items():
                    # try:
                        # Skip if role exists
                        if await auth_service.get_role_by_name(template_name, session):
                            continue
                            
                        # Get permission IDs
                        permission_ids = []
                        for perm_name in template["permissions"]:
                            perm = await auth_service.get_permission_by_name(perm_name, session)
                            if perm:
                                permission_ids.append(perm.id)
                        
                        # Create role
                        if permission_ids:
                            await auth_service.create_role(template_name, permission_ids, actor=system_user, session=session)
                            roles_created += 1
                            
                    # except Exception as e:
                    #     click.echo(f"Error creating role '{template_name}': {e}")
                    #     raise e
                
                click.echo(f"Created {roles_created} roles")
                await session.commit()
            # except Exception as e:
            #     await session.rollback()
            #     raise click.ClickException(str(e))
            
    asyncio.run(run())

if __name__ == '__main__':
    cli()