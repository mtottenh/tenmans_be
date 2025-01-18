from typing import List, Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
import uuid
from datetime import datetime

from auth.models import PlayerRole, Role, Permission, RolePermission
from audit.service import AuditService

class RoleServiceError(Exception):
    """Base exception for role service errors"""
    pass

class RoleService:
    def __init__(self):
        self.audit_service = AuditService()

    def _role_audit_details(self, role: Role) -> dict:
        """Extract audit details from a role operation"""
        return {
            "role_id": str(role.id),
            "role_name": role.name,
            "created_at": role.created_at.isoformat() if role.created_at else None
        }

    async def get_role(self, role_id: uuid.UUID, session: AsyncSession) -> Optional[Role]:
        """Get a role by ID"""
        stmt = select(Role).where(Role.id == role_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_role_by_name(self, name: str, session: AsyncSession) -> Optional[Role]:
        """Get a role by name"""
        stmt = select(Role).where(Role.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_roles_by_names(self, names: List[str], session: AsyncSession) -> List[Role]:
        stmt = select(Role).where(Role.name.in_(names))
        result = await session.execute(stmt)
        return result.scalars().all()
    
    async def get_all_roles(self, session: AsyncSession) -> List[Role]:
        """Get all roles"""
        stmt = select(Role)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_permission(self, permission_id: uuid.UUID, session: AsyncSession) -> Optional[Permission]:
        """Get a permission by ID"""
        stmt = select(Permission).where(Permission.id == permission_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_permission_by_name(self, name: str, session: AsyncSession) -> Optional[Permission]:
        """Get a permission by name"""
        stmt = select(Permission).where(Permission.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_permissions(self, session: AsyncSession) -> List[Permission]:
        """Get all permissions"""
        stmt = select(Permission)
        result = await session.execute(stmt)
        return result.scalars().all()

    @AuditService.audited_transaction(
        action_type="role_create",
        entity_type="role",
        details_extractor=_role_audit_details
    )
    async def create_role(self, name: str, permission_ids: List[uuid.UUID], actor, session: AsyncSession) -> Role:
        """Create a new role with permissions"""
        # Check if role already exists
        existing_role = await self.get_role_by_name(name, session)
        if existing_role:
            raise RoleServiceError(f"Role '{name}' already exists")

        # Verify all permissions exist
        permissions = []
        for perm_id in permission_ids:
            permission = await self.get_permission(perm_id, session)
            if not permission:
                raise RoleServiceError(f"Permission {perm_id} not found")
            permissions.append(permission)

        # Create role
        role = Role(name=name, created_at=datetime.now())
        role.permissions = permissions
        session.add(role)
        return role

    @AuditService.audited_transaction(
        action_type="role_update",
        entity_type="role",
        details_extractor=_role_audit_details
    )
    async def update_role(
        self,
        role_id: uuid.UUID,
        permission_ids: List[uuid.UUID],
        actor,
        session: AsyncSession
    ) -> Role:
        """Update a role's permissions"""
        role = await self.get_role(role_id, session)
        if not role:
            raise RoleServiceError("Role not found")

        # Verify all permissions exist
        permissions = []
        for perm_id in permission_ids:
            permission = await self.get_permission(perm_id, session)
            if not permission:
                raise RoleServiceError(f"Permission {perm_id} not found")
            permissions.append(permission)

        # Update role permissions
        role.permissions = permissions
        session.add(role)
        return role

    @AuditService.audited_transaction(
        action_type="role_delete",
        entity_type="role",
        details_extractor=_role_audit_details
    )
    async def delete_role(self, role_id: uuid.UUID, actor, session: AsyncSession) -> Role:
        """Delete a role"""
        role = await self.get_role(role_id, session)
        if not role:
            raise RoleServiceError("Role not found")

        # Remove role from all players
        stmt = select(PlayerRole).where(PlayerRole.role_id == role_id)
        result = await session.execute(stmt)
        player_roles = result.scalars().all()

        for pr in player_roles:
            await session.delete(pr)

        await session.delete(role)
        return role

    async def create_permission(
        self,
        name: str,
        description: str,
        
        session: AsyncSession
    ) -> Permission:
        """Create a new permission"""
        # Check if permission already exists
        existing_permission = await self.get_permission_by_name(name, session)
        if existing_permission:
            raise RoleServiceError(f"Permission '{name}' already exists")

        permission = Permission(
            name=name,
            description=description,
            created_at=datetime.now()
        )
        session.add(permission)
        await session.commit()
        await session.refresh(permission)
        return permission

    async def delete_permission(
        self,
        permission_id: uuid.UUID,
        session: AsyncSession
    ) -> Permission:
        """Delete a permission"""
        permission = await self.get_permission(permission_id, session)
        if not permission:
            raise RoleServiceError("Permission not found")

        # Remove permission from all roles
        stmt = select(RolePermission).where(RolePermission.permission_id == permission_id)
        result = await session.execute(stmt)
        role_permissions = result.scalars().all()

        for rp in role_permissions:
            await session.delete(rp)

        await session.delete(permission)
        await session.commit()
        return permission