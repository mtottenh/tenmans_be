from typing import Any, List, Optional, Tuple
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
import uuid
from datetime import datetime
from auth.models import Player, Role, Permission, PlayerRole, RolePermission
from auth.schemas import ScopeType
from audit.service import AuditService

class PermissionServiceError(Exception):
    """Base exception for permission operations"""
    pass

class PermissionScope:
    def __init__(self, scope_type: ScopeType, scope_id: Optional[uuid.UUID] = None):
        self.scope_type = scope_type
        self.scope_id = scope_id

    def __eq__(self, other):
        if not isinstance(other, PermissionScope):
            return False
        return (self.scope_type == other.scope_type and 
                self.scope_id == other.scope_id)

class PermissionService:
    """Service for handling roles, permissions, and access control"""
    
    def __init__(self, audit_service: Optional[AuditService] = None):
        self.audit_service = audit_service or AuditService()

    def _permission_audit_details(self, permission: Permission) -> dict:
        """Extract audit details from a permission operation"""
        return {
            "permission_id": str(permission.id),
            "permission_name": permission.name,
            "description": permission.description,
            "created_at": permission.created_at.isoformat() if permission.created_at else None
        }

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
        action_type="permission_create",
        entity_type="permission",
        details_extractor=_permission_audit_details
    )
    async def create_permission(
        self,
        name: str,
        description: str,
        actor: Any,
        session: AsyncSession
    ) -> Permission:
        """Create a new permission"""
        existing = await self.get_permission_by_name(name, session)
        if existing:
            raise PermissionServiceError(f"Permission '{name}' already exists")

        permission = Permission(
            name=name,
            description=description,
            created_at=datetime.now()
        )
        session.add(permission)
        return permission

    @AuditService.audited_deletion(
        action_type="permission_delete",
        entity_type="permission",
        details_extractor=_permission_audit_details
    )
    async def delete_permission(
        self,
        permission_id: uuid.UUID,
        actor: Any,
        session: AsyncSession
    ) -> Permission:
        """Delete a permission"""
        permission = await self.get_permission(permission_id, session)
        if not permission:
            raise PermissionServiceError("Permission not found")

        # Remove permission from all roles
        stmt = select(RolePermission).where(RolePermission.permission_id == permission_id)
        result = await session.execute(stmt)
        role_permissions = result.scalars().all()

        for rp in role_permissions:
            await session.delete(rp)

        await session.delete(permission)
        return permission

    async def get_player_permissions(
        self,
        player: Player,
        session: AsyncSession
    ) -> List[Tuple[str, ScopeType, Optional[uuid.UUID]]]:
        """Get all permissions for a player with their scopes"""
        stmt = select(
            Permission.name,
            PlayerRole.scope_type,
            PlayerRole.scope_id
        ).join(
            Role,
            Permission.roles
        ).join(
            PlayerRole,
            Role.id == PlayerRole.role_id
        ).where(
            PlayerRole.player_id == player.id
        )
        
        result = await session.execute(stmt)
        #         [(PermissionName, ScopeType, ScopeID)]
        return [(row[0], ScopeType(row[1]), row[2]) for row in result]


    async def verify_permissions(
        self,
        player: Player,
        required_permissions: List[str],
        scope: Optional[PermissionScope],
        session: AsyncSession
    ) -> bool:
        """Verify if player has all required permissions in scope"""
        player_permissions = await self.get_player_permissions(player, session)
        
        for required_perm in required_permissions:
            has_permission = False
            for perm_name, perm_scope_type, perm_scope_id in player_permissions:
                if perm_name != required_perm:
                    continue

                if perm_scope_type == ScopeType.GLOBAL:
                    has_permission = True
                    break

                if scope and perm_scope_type == scope.scope_type:
                    if scope.scope_id is None or perm_scope_id == scope.scope_id:
                        has_permission = True
                        break

            if not has_permission:
                return False

        return True
    
def create_permission_service(audit_svc: Optional[AuditService] = None) -> PermissionService:
    audit_service = audit_svc or AuditService()
    return PermissionService(audit_service)
