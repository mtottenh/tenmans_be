# permissions/manager.py

import logging
from typing import List, Optional
import uuid
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Player, Role, PlayerRole, VerificationStatus, AuthType
from auth.service import AuthService, ScopeType
from teams.models import Team
from competitions.models.tournaments import Tournament
from roles.models import PermissionTemplate
from roles.service import RoleService

logger = logging.getLogger(__name__)

class PermissionManager:
    """Core service for managing user permissions"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth_service = AuthService()
        self.role_service = RoleService(session)

    async def create_initial_admin(self, steam_id: str, email: Optional[str] = None) -> Player:
        """Create initial admin user if no admin exists"""
        # Check if any admin exists
        stmt = select(Player).join(PlayerRole).join(Role).where(Role.name == "admin")
        result = await self.session.execute(stmt)
        if result.first():
            raise ValueError("Admin user already exists")

        # Create admin role if it doesn't exist
        admin_role = await self.role_service.get_or_create_admin_role()

        # Create the player
        player = Player(
            steam_id=steam_id,
            email=email,
            name="Initial Admin",
            auth_type=AuthType.STEAM if not email else AuthType.EMAIL,
            verification_status=VerificationStatus.VERIFIED
        )
        self.session.add(player)
        await self.session.flush()

        # Assign admin role
        await self.auth_service.assign_role(
            player=player,
            role=admin_role,
            scope_type=ScopeType.GLOBAL,
            scope_id=None,
            session=self.session
        )

        await self.session.commit()
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
            # Get or create role with template permissions
            role = await self.role_service.get_or_create_role(
                role_name,
                template["permissions"]
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

    def _check_permission_conflicts(self, *args, **kwargs):
        """Handle potential permission conflicts"""
        pass  # Implementation depends on your specific conflict rules