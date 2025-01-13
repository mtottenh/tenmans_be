# permissions/role_service.py

import logging
from typing import List
import uuid
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Role, Permission, PlayerRole

logger = logging.getLogger(__name__)

class RoleService:
    """Service for managing roles and their permissions"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_role(self, name: str, permissions: List[str]) -> Role:
        """Create a new role with specified permissions"""
        # Check if role exists
        stmt = select(Role).where(Role.name == name)
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Role {name} already exists")

        # Create role
        role = Role(name=name)
        self.session.add(role)
        await self.session.flush()

        # Get and assign permissions
        stmt = select(Permission).where(Permission.name.in_(permissions))
        result = await self.session.execute(stmt)
        role.permissions = result.scalars().all()

        if len(role.permissions) != len(permissions):
            missing = set(permissions) - {p.name for p in role.permissions}
            raise ValueError(f"Invalid permissions: {missing}")

        await self.session.commit()
        return role

    async def edit_role(self, role_id: uuid.UUID, new_permissions: List[str]) -> Role:
        """Edit an existing role's permissions"""
        role = await self.session.get(Role, role_id)
        if not role:
            raise ValueError(f"Role {role_id} not found")

        # Get new permissions
        stmt = select(Permission).where(Permission.name.in_(new_permissions))
        result = await self.session.execute(stmt)
        permissions = result.scalars().all()

        if len(permissions) != len(new_permissions):
            missing = set(new_permissions) - {p.name for p in permissions}
            raise ValueError(f"Invalid permissions: {missing}")

        role.permissions = permissions
        await self.session.commit()
        return role

    async def delete_role(self, role_id: uuid.UUID):
        """Delete a role and remove it from all users"""
        role = await self.session.get(Role, role_id)
        if not role:
            raise ValueError(f"Role {role_id} not found")

        # Remove role from all users
        stmt = select(PlayerRole).where(PlayerRole.role_id == role_id)
        result = await self.session.execute(stmt)
        player_roles = result.scalars().all()

        for pr in player_roles:
            await self.session.delete(pr)

        await self.session.delete(role)
        await self.session.commit()

    async def get_or_create_role(self, name: str, permissions: List[str]) -> Role:
        """Get existing role or create new one with specified permissions"""
        stmt = select(Role).where(Role.name == name)
        result = await self.session.execute(stmt)
        role = result.scalar_one_or_none()

        if not role:
            role = await self.create_role(name, permissions)

        return role

    async def get_or_create_admin_role(self) -> Role:
        """Get or create the admin role with all permissions"""
        # Check if admin role exists
        stmt = select(Role).where(Role.name == "admin")
        result = await self.session.execute(stmt)
        admin_role = result.scalar_one_or_none()
        
        if not admin_role:
            # Create admin role
            admin_role = Role(name="admin")
            self.session.add(admin_role)
            await self.session.flush()

            # Get all permissions
            stmt = select(Permission)
            result = await self.session.execute(stmt)
            permissions = result.scalars().all()

            # Assign all permissions to admin role
            admin_role.permissions = permissions
            await self.session.commit()

        return admin_role