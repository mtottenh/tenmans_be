import logging
from typing import List, Optional
import uuid
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Player, Role, PlayerRole, AuthType
from auth.schemas import Permission, PlayerStatus
from auth.service.auth import  ScopeType
from auth.schemas import PermissionTemplate
from services.auth import auth_service
logger = logging.getLogger(__name__)

class PermissionManager:
    """Core service for managing user permissions"""
    
    def __init__(self, session: AsyncSession, system_user: Player):
        self.session = session
        self.auth_service = auth_service
        #self.auth_service = create_auth_service()
        self.system_user = system_user

    async def create_initial_admin(self, steam_id: str, email: Optional[str] = None) -> Player:
        """Create initial admin user if no admin exists"""
        # Check if any admin exists
        stmt = select(Player).join(PlayerRole).join(Role).where(Role.name == "league_admin")
        result = await self.session.execute(stmt)
        if result.first():
            raise ValueError("Admin user already exists")

        # Create admin role if it doesn't exist
        admin_role = await self.auth_service.get_role_by_name("league_admin", self.session)
        if not admin_role:
            # Get or create all admin permissions
            permissions = await self._ensure_admin_permissions()
            # Create admin role with all permissions
            admin_role = await self.auth_service.create_role(
                "league_admin",
                [p.id for p in permissions],
                actor=self.system_user,
                session=self.session
            )

        # Create the player
        player = Player(
            steam_id=steam_id,
            email=email,
            name="Initial Admin",
            auth_type=AuthType.STEAM if not email else AuthType.EMAIL,
            status=PlayerStatus.ACTIVE
        )
        self.session.add(player)
        await self.session.flush()
        await self.session.refresh(player)
        # Assign admin role
        await self.auth_service.assign_role(
            player=player,
            role=admin_role,
            scope_type=ScopeType.GLOBAL,
            scope_id=None,
            session=self.session
        )

        await self.session.commit()
        await self.session.refresh(player)
        return player

    async def apply_template(
        self,
        player: Player,
        template_name: str,
        scope_id: Optional[uuid.UUID] = None
    ) -> List[Role]:
        """Apply a permission template to a player"""
        template = PermissionTemplate.get_template(template_name)
        roles = []

        for role_name in template["roles"]:
            # Get or create role using RoleService
            role = await self.auth_service.get_role_by_name(role_name, self.session)
            if not role:
                # Get permissions for the role
                permission_ids = []
                for perm_name in template["permissions"]:
                    perm = await self.auth_service.get_permission_by_name(perm_name, self.session)
                    if not perm:
                        # Create permission if it doesn't exist
                        perm = await self.auth_service.create_permission(
                            name=perm_name,
                            description=f"Permission to {perm_name.replace('_', ' ')}",
                            session=self.session
                        )
                    permission_ids.append(perm.id)
                
                # Create role with permissions
                role = await self.auth_service.create_role(
                    name=role_name,
                    permission_ids=permission_ids,
                    actor=self.system_user,
                    session=self.session
                )
            
            roles.append(role)

            # Assign role with appropriate scope
            await self.auth_service.assign_role(
                player=player,
                role=role,
                scope_type=template["scope_type"],
                scope_id=scope_id,
                session=self.session
            )

        return roles

    async def _ensure_admin_permissions(self) -> List[Permission]:
        """Ensure all admin permissions exist and return them"""
        admin_permissions = [
            "manage_users",
            "manage_roles",
            "manage_permissions",
            "manage_seasons",
            "manage_tournaments",
            "manage_teams",
            "manage_bans",
            "verify_users",
            "moderate_chat",
            "manage_reports",
            "admin_override"
        ]
        
        permissions = []
        for perm_name in admin_permissions:
            perm = await self.auth_service.get_permission_by_name(perm_name, self.session)
            if not perm:
                perm = await self.auth_service.create_permission(
                    name=perm_name,
                    description=f"Admin permission to {perm_name.replace('_', ' ')}",
                    session=self.session
                )
            permissions.append(perm)
            
        return permissions