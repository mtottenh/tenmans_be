import logging
from typing import List, Optional, Dict, Tuple
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Player, Role, Permission
from auth.service import ScopeType
from teams.models import Team
from competitions.models.tournaments import Tournament
from .manager import PermissionManager
from roles.service import RoleService
from roles.models import PermissionTemplate
import uuid

logger = logging.getLogger(__name__)

class PermissionUI:
    """Interactive UI for permission management"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.manager = PermissionManager(session)
        self.role_service = RoleService(session)

    async def edit_permissions(self, player_uid: str):
        """Interactive permission editor for a player"""
        player = await self._get_player(player_uid)
        if not player:
            print(f"Error: Player {player_uid} not found")
            return

        while True:
            await self._show_current_permissions(player)
            
            print("\nPermission Management Options:")
            print("1. Add Role")
            print("2. Remove Role")
            print("3. Apply Template")
            print("4. Show Current Permissions")
            print("5. Exit")

            choice = input("\nEnter choice (1-5): ")

            try:
                if choice == "1":
                    await self._add_role_flow(player)
                elif choice == "2":
                    await self._remove_role_flow(player)
                elif choice == "3":
                    await self._apply_template_flow(player)
                elif choice == "4":
                    continue  # Will show permissions again
                elif choice == "5":
                    break
                else:
                    print("Invalid choice")
            except Exception as e:
                print(f"Error: {e}")

    async def manage_roles(self):
        """Interactive role management interface"""
        while True:
            print("\nRole Management Options:")
            print("1. List Roles")
            print("2. Create Role")
            print("3. Edit Role")
            print("4. Delete Role")
            print("5. Exit")

            choice = input("\nEnter choice (1-5): ")

            try:
                if choice == "1":
                    await self._list_roles()
                elif choice == "2":
                    await self._create_role_flow()
                elif choice == "3":
                    await self._edit_role_flow()
                elif choice == "4":
                    await self._delete_role_flow()
                elif choice == "5":
                    break
                else:
                    print("Invalid choice")
            except Exception as e:
                print(f"Error: {e}")

    async def _show_current_permissions(self, player: Player):
        """Display current permissions for a player"""
        print(f"\nCurrent Permissions for {player.name}")
        print("=" * 50)

        # Get roles and permissions
        roles_and_scopes = await self.manager.auth_service.get_player_roles(
            player,
            self.session
        )

        if not roles_and_scopes:
            print("No roles assigned")
            return

        for role, scope_type, scope_id in roles_and_scopes:
            # Get scope name if applicable
            scope_info = await self._get_scope_info(scope_type, scope_id)
            
            print(f"\nRole: {role.name}")
            print(f"Scope: {scope_type.value}{scope_info}")
            print("Permissions:")
            for perm in role.permissions:
                print(f"  - {perm.name}")

    async def _add_role_flow(self, player: Player):
        """Flow for adding a role to a player"""
        # Get available roles
        roles = await self._get_all_roles()
        if not roles:
            print("No roles available")
            return

        print("\nAvailable Roles:")
        for i, role in enumerate(roles, 1):
            print(f"{i}. {role.name}")

        try:
            choice = int(input("\nSelect role number: ")) - 1
            if 0 <= choice < len(roles):
                role = roles[choice]
                
                # Get scope
                scope_type, scope_id = await self._get_scope_selection()
                
                # Assign role
                await self.manager.auth_service.assign_role(
                    player=player,
                    role=role,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    session=self.session
                )
                print(f"\nAdded role {role.name}")
        except ValueError:
            print("Invalid selection")

    async def _remove_role_flow(self, player: Player):
        """Flow for removing a role from a player"""
        roles_and_scopes = await self.manager.auth_service.get_player_roles(
            player,
            self.session
        )
        
        if not roles_and_scopes:
            print("Player has no roles to remove")
            return

        print("\nCurrent Roles:")
        for i, (role, scope_type, scope_id) in enumerate(roles_and_scopes, 1):
            scope_info = await self._get_scope_info(scope_type, scope_id)
            print(f"{i}. {role.name} - {scope_type.value}{scope_info}")

        try:
            choice = int(input("\nSelect role to remove (number): ")) - 1
            if 0 <= choice < len(roles_and_scopes):
                role, scope_type, scope_id = roles_and_scopes[choice]
                
                # Remove the role
                await self.manager.auth_service.remove_role(
                    player=player,
                    role=role,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    session=self.session
                )
                print(f"\nRemoved role {role.name}")
        except ValueError:
            print("Invalid selection")

    async def _apply_template_flow(self, player: Player):
        """Flow for applying a permission template"""
        print("\nAvailable Templates:")
        templates = PermissionTemplate.list_templates()
        for i, template in enumerate(templates, 1):
            print(f"{i}. {template}")

        try:
            choice = int(input("\nSelect template number: ")) - 1
            if 0 <= choice < len(templates):
                template_name = templates[choice]
                template = PermissionTemplate.get_template(template_name)

                scope_id = None
                if template["scope_type"] != ScopeType.GLOBAL:
                    scope_id = await self._get_scope_id(template["scope_type"])

                roles = await self.manager.apply_template(
                    player,
                    template_name,
                    scope_id
                )
                print(f"\nApplied template '{template_name}'")
                
        except ValueError:
            print("Invalid selection")

    async def _create_role_flow(self):
        """Flow for creating a new role"""
        name = input("Enter role name: ").strip()
        if not name:
            print("Role name cannot be empty")
            return

        print("\nAvailable Permissions:")
        permissions = await self._get_all_permissions()
        for i, perm in enumerate(permissions, 1):
            print(f"{i}. {perm.name}")

        perm_input = input("\nEnter permission numbers (comma-separated): ")
        try:
            selected_indices = [int(i.strip()) - 1 for i in perm_input.split(",")]
            selected_perms = [
                permissions[i].name for i in selected_indices
                if 0 <= i < len(permissions)
            ]
            
            if selected_perms:
                await self.role_service.create_role(name, selected_perms)
                print(f"\nCreated role: {name}")
            else:
                print("No valid permissions selected")
        except ValueError:
            print("Invalid input")

    async def _edit_role_flow(self):
        """Flow for editing an existing role"""
        roles = await self._get_all_roles()
        if not roles:
            print("No roles available")
            return

        print("\nAvailable Roles:")
        for i, role in enumerate(roles, 1):
            print(f"{i}. {role.name}")

        try:
            role_idx = int(input("\nSelect role to edit: ")) - 1
            if 0 <= role_idx < len(roles):
                role = roles[role_idx]
                
                print("\nCurrent Permissions:")
                permissions = await self._get_all_permissions()
                for i, perm in enumerate(permissions, 1):
                    has_perm = perm in role.permissions
                    mark = "✓" if has_perm else " "
                    print(f"{i}. [{mark}] {perm.name}")

                perm_input = input("\nEnter new permission numbers (comma-separated): ")
                selected_indices = [int(i.strip()) - 1 for i in perm_input.split(",")]
                selected_perms = [
                    permissions[i].name for i in selected_indices
                    if 0 <= i < len(permissions)
                ]
                
                if selected_perms:
                    await self.role_service.edit_role(role.id, selected_perms)
                    print(f"\nUpdated role: {role.name}")
                else:
                    print("No valid permissions selected")
        except ValueError:
            print("Invalid input")

    async def _delete_role_flow(self):
        """Flow for deleting a role"""
        roles = await self._get_all_roles()
        if not roles:
            print("No roles available")
            return

        print("\nAvailable Roles:")
        for i, role in enumerate(roles, 1):
            print(f"{i}. {role.name}")

        try:
            role_idx = int(input("\nSelect role to delete: ")) - 1
            if 0 <= role_idx < len(roles):
                role = roles[role_idx]
                confirm = input(f"Are you sure you want to delete {role.name}? (y/N): ")
                if confirm.lower() == 'y':
                    await self.role_service.delete_role(role.id)
                    print(f"\nDeleted role: {role.name}")
        except ValueError:
            print("Invalid input")

    # Helper methods
    async def _get_player(self, player_uid: str) -> Optional[Player]:
        """Get player by UID"""
        return await self.manager.auth_service.get_player_by_uid(
            player_uid,
            self.session
        )

    async def _get_all_roles(self) -> List[Role]:
        """Get all available roles"""
        stmt = select(Role)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def _get_all_permissions(self) -> List[Permission]:
        """Get all available permissions"""
        stmt = select(Permission)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def _get_scope_selection(self) -> Tuple[ScopeType, Optional[uuid.UUID]]:
        """Get scope type and ID from user input"""
        print("\nScope types:")
        print("1. Global")
        print("2. Team")
        print("3. Tournament")

        scope_choice = input("Select scope type (1-3): ")
        
        if scope_choice == "1":
            return ScopeType.GLOBAL, None
        elif scope_choice == "2":
            scope_id = await self._get_scope_id(ScopeType.TEAM)
            return ScopeType.TEAM, scope_id
        elif scope_choice == "3":
            scope_id = await self._get_scope_id(ScopeType.TOURNAMENT)
            return ScopeType.TOURNAMENT, scope_id
        else:
            raise ValueError("Invalid scope type")

    async def _get_scope_id(self, scope_type: ScopeType) -> Optional[uuid.UUID]:
        """Get scope ID based on type"""
        if scope_type == ScopeType.TEAM:
            # List teams
            stmt = select(Team)
            result = await self.session.execute(stmt)
            teams = result.scalars().all()
            
            print("\nSelect team:")
            for i, team in enumerate(teams, 1):
                print(f"{i}. {team.name}")
            
            choice = int(input("Team number: ")) - 1
            if 0 <= choice < len(teams):
                return teams[choice].id
                
        elif scope_type == ScopeType.TOURNAMENT:
            # List tournaments
            stmt = select(Tournament)
            result = await self.session.execute(stmt)
            tournaments = result.scalars().all()
            
            print("\nSelect tournament:")
            for i, tournament in enumerate(tournaments, 1):
                print(f"{i}. {tournament.name}")
            
            choice = int(input("Tournament number: ")) - 1
            if 0 <= choice < len(tournaments):
                return tournaments[choice].id
                
        return None

    async def _get_scope_info(
        self,
        scope_type: ScopeType,
        scope_id: Optional[uuid.UUID]
    ) -> str:
        """Get readable scope information"""
        if not scope_id:
            return ""
            
        if scope_type == ScopeType.TEAM:
            team = await self.session.get(Team, scope_id)
            return f" - {team.name}" if team else ""
            
        elif scope_type == ScopeType.TOURNAMENT:
            tournament = await self.session.get(Tournament, scope_id)
            return f" - {tournament.name}" if tournament else ""
            
        return ""