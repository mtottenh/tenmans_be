import logging
from typing import List, Optional, Tuple
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from auth.models import Player, Role
from auth.service.auth import create_auth_service, ScopeType
from teams.models import Team
from competitions.models.tournaments import Tournament
from auth.service.role import create_role_service
from auth.schemas import PermissionTemplate
import uuid
from services.auth import auth_service

logger = logging.getLogger(__name__)

class PermissionUI:
    """Interactive UI for permission management"""
    
    def __init__(self, system_user, session: AsyncSession):
        self.session = session
        self.auth_service = auth_service
        self.system_user = system_user

    async def edit_permissions(self, player_id: str):
        """Interactive permission editor for a player"""
        player = await self.auth_service.get_player_by_id(player_id, self.session)
        if not player:
            print(f"Error: Player {player_id} not found")
            return
        await self.session.flush()
        
        while True:
            await self.session.refresh(player)
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
                raise

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

        # Get roles and permissions using auth service
        roles_and_scopes = await self.auth_service.get_player_roles(
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
            for perm in await role.awaitable_attrs.permissions:
                print(f"  - {perm.name}: {perm.description}")

    async def _add_role_flow(self, player: Player):
        """Flow for adding a role to a player"""
        # Get available roles
        
        roles = await self.auth_service.get_all_roles(self.session)
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
                await self.auth_service.assign_role(
                    player=player,
                    role=role,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    actor=self.system_user,
                    session=self.session
                )
                await self.session.refresh(player)
                await self.session.refresh(role)
                print(f"\nAdded role {role.name}")
                

        except ValueError as e:
            print(f"Invalid selection {str(e)}")

    async def _remove_role_flow(self, player: Player):
        """Flow for removing a role from a player"""
        roles_and_scopes = await self.auth_service.get_player_roles(
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
                
                
                await self.auth_service.remove_role_from_player(
                    player=player,
                    role=role,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    actor=self.system_user,
                    session=self.session
                )
                await self.session.refresh(player)
                await self.session.refresh(role)
                print(f"\nRemoved role {role.name}")
        except Exception:
            raise 

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

                # Create and assign roles from template
                await self._create_template_roles(template_name, template)

                # Apply template to player
                roles = await self._apply_template_to_player(
                    player,
                    template_name,
                    scope_id
                )
                print(f"\nApplied template '{template_name}' with {len(roles)} roles")
                
        except ValueError:
            print("Invalid selection")

    async def _create_role_flow(self):
        """Flow for creating a new role"""
        name = input("Enter role name: ").strip()
        if not name:
            print("Role name cannot be empty")
            return

        print("\nAvailable Permissions:")
        permissions = await self.auth_service.get_all_permissions(self.session)
        for i, perm in enumerate(permissions, 1):
            print(f"{i}. {perm.name}: {perm.description}")

        perm_input = input("\nEnter permission numbers (comma-separated): ")
        try:
            selected_indices = [int(i.strip()) - 1 for i in perm_input.split(",")]
            perm_ids = []
            for idx in selected_indices:
                if 0 <= idx < len(permissions):
                    perm_ids.append(permissions[idx].id)
            
            if perm_ids:
                role = await self.auth_service.create_role(name, perm_ids, self.session)
                print(f"\nCreated role: {role.name}")
            else:
                print("No valid permissions selected")
        except ValueError:
            print("Invalid input")

    async def _edit_role_flow(self):
        """Flow for editing an existing role"""
        roles = await self.auth_service.get_all_roles(self.session)
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
                
                print("\nAvailable Permissions:")
                permissions = await self.auth_service.get_all_permissions(self.session)
                for i, perm in enumerate(permissions, 1):
                    has_perm = perm in await role.awaitable_attrs.permissions
                    mark = "✓" if has_perm else " "
                    print(f"{i}. [{mark}] {perm.name}: {perm.description}")

                perm_input = input("\nEnter new permission numbers (comma-separated): ")
                selected_indices = [int(i.strip()) - 1 for i in perm_input.split(",")]
                perm_ids = []
                for idx in selected_indices:
                    if 0 <= idx < len(permissions):
                        perm_ids.append(permissions[idx].id)
                
                if perm_ids:
                    role = await self.auth_service.update_role(role.id, perm_ids, self.session)
                    print(f"\nUpdated role: {role.name}")
                else:
                    print("No valid permissions selected")
        except ValueError:
            print("Invalid input")

    async def _delete_role_flow(self):
        """Flow for deleting a role"""
        roles = await self.auth_service.get_all_roles(self.session)
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
                    await self.auth_service.delete_role(role.id, self.session)
                    print(f"\nDeleted role: {role.name}")
        except ValueError:
            print("Invalid input")

    async def _create_template_roles(self, template_name: str, template: dict):
        """Create roles defined in a template if they don't exist"""
        for role_name in template["roles"]:
            if not await self.auth_service.get_role_by_name(role_name, self.session):
                # Get permission IDs
                perm_ids = []
                for perm_name in template["permissions"]:
                    perm = await self.auth_service.get_permission_by_name(perm_name, self.session)
                    if not perm:
                        # Create permission if it doesn't exist
                        perm = await self.auth_service.create_permission(
                            name=perm_name,
                            description=f"Permission to {perm_name.replace('_', ' ')}",
                            session=self.session
                        )
                    perm_ids.append(perm.id)
                
                # Create role
                await self.auth_service.create_role(role_name, perm_ids, self.session)

    async def _apply_template_to_player(
        self,
        player: Player,
        template_name: str,
        scope_id: Optional[uuid.UUID]
    ) -> List[Role]:
        """Apply template roles to a player"""
        template = PermissionTemplate.get_template(template_name)
        roles = []
        
        for role_name in template["roles"]:
            role = await self.auth_service.get_role_by_name(role_name, self.session)
            if not role:
                continue
                
            roles.append(role)
            await self.auth_service.assign_role(
                player=player,
                role=role,
                scope_type=template["scope_type"],
                scope_id=scope_id,
                session=self.session
            )
            
        return roles

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