from typing import Any, Dict, List, Optional, Tuple
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
import uuid
from datetime import datetime

from audit.context import AuditContext
from audit.models import AuditEventType
from auth.models import Player, PlayerRole, Role
from audit.service import AuditService
from auth.schemas import ScopeType
from auth.service.permission import PermissionService

class RoleServiceError(Exception):
    """Base exception for role service errors"""
    pass

class RoleService:
    def __init__(self, permission_service: PermissionService):
        self.permission_service = permission_service

    def _role_audit_details(self, role: Role, context: Dict) -> dict:
        """Extract audit details from a role operation"""
        return {
            "role_id": str(role.id),
            "role_name": role.name,
            "created_at": role.created_at.isoformat() if role.created_at else None
        }
    
    def _player_role_audit_details(self, role: PlayerRole,  context: Dict) -> dict:
        return {
            "role_id": str(role.role_id),
            "scope_id": str(role.scope_id),
            "scope_type": str(role.scope_type),
            "created_at": role.created_at.isoformat() if role.created_at else None
        }
    # We need to make a uuid up as the PlayerRole() table has no primary key
    def _id_extractor_player_role(self, role: Role) -> uuid:
        return uuid.uuid4()

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

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type='Role',
        details_extractor=_role_audit_details
    )
    async def create_role(self, name: str, 
                          permission_ids: List[uuid.UUID], 
                          actor, 
                          session: AsyncSession,
                          audit_context: Optional[AuditContext] = None
                          ) -> Role:
        """Create a new role with permissions"""
        # Check if role already exists
        existing_role = await self.get_role_by_name(name, session)
        if existing_role:
            raise RoleServiceError(f"Role '{name}' already exists")

        # Verify all permissions exist
        permissions = []
        for perm_id in permission_ids:
            permission = await self.permission_service.get_permission(perm_id, session)
            if not permission:
                raise RoleServiceError(f"Permission {perm_id} not found")
            permissions.append(permission)

        # Create role
        role = Role(name=name, created_at=datetime.now())
        role.permissions = permissions
        session.add(role)
        return role

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Role",
        details_extractor=_role_audit_details
    )
    async def update_role(
        self,
        role_id: uuid.UUID,
        permission_ids: List[uuid.UUID],
        actor: Any,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Role:
        """Update a role's permissions"""
        role = await self.get_role(role_id, session)
        if not role:
            raise RoleServiceError("Role not found")

        # Verify all permissions exist
        permissions = []
        for perm_id in permission_ids:
            permission = await self.permission_service.get_permission(perm_id, session)
            if not permission:
                raise RoleServiceError(f"Permission {perm_id} not found")
            permissions.append(permission)

        # Update role permissions
        role.permissions = permissions
        session.add(role)
        return role

    @AuditService.audited_transaction(
        action_type=AuditEventType.DELETE,
        entity_type="Role",
        details_extractor=_role_audit_details
    )
    async def delete_role(
        self,
        role_id: uuid.UUID,
        actor: Any,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Role:
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

    async def verify_role(self,
        player: Player,
        allowed_roles: List[str],
        session: AsyncSession
    ) -> bool:
        """Check if player has any of the allowed roles"""
        player_roles = await self.get_player_roles(player, session)
        player_role_names = {role.name for role, _, _ in player_roles}
        return bool(player_role_names & set(allowed_roles))

    async def get_player_roles(
        self,
        player: Player,
        session: AsyncSession
    ) -> List[Tuple[Role, ScopeType, Optional[uuid.UUID]]]:
        """Get all roles for a player with their scopes"""
        stmt = select(
            Role,
            PlayerRole.scope_type,
            PlayerRole.scope_id
        ).join(
            PlayerRole,
            Role.id == PlayerRole.role_id
        ).where(
            PlayerRole.player_id == player.id
        )
        
        result = await session.execute(stmt)
        return [(row[0], ScopeType(row[1]), row[2]) for row in result]
    

############# TODO - BELONGS IN ADMIN_SERVICE? ######################
    @AuditService.audited_transaction(
        action_type=AuditEventType.ROLE_CHANGE,
        entity_type="PlayerRole",
        details_extractor=_player_role_audit_details,
        id_extractor=_id_extractor_player_role
    )
    async def assign_role(
        self,
        player: Player,
        role: Role,
        scope_type: ScopeType,
        scope_id: Optional[uuid.UUID],
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> PlayerRole:
        """Assign a role to a player"""
        if scope_type != ScopeType.GLOBAL and scope_id is None:
            raise ValueError("scope_id is required for non-global scopes")

        player_role = PlayerRole(
            player_id=player.id,
            role_id=role.id,
            scope_type=scope_type,
            scope_id=scope_id
        )
        
        session.add(player_role)
        return player_role

    @AuditService.audited_transaction(
        action_type=AuditEventType.DELETE,
        entity_type="PlayerRole",
        details_extractor=_player_role_audit_details,
        id_extractor=_id_extractor_player_role
    )
    async def delete_player_role(self, player_role: PlayerRole, actor: Player, session: AsyncSession, audit_context: Optional[AuditContext] = None):
            
        return await session.delete(player_role)


    async def remove_role_from_player(
        self,
        player: Player,
        role: Role,
        scope_type: ScopeType,
        scope_id: Optional[uuid.UUID],
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
        ):
        """Remove a role assignment from a player"""
        if scope_type != ScopeType.GLOBAL and scope_id is None:
            raise ValueError("scope_id is required for non-global scopes")
        
        stmt = select(
            PlayerRole
        ).where(
            PlayerRole.player_id == player.id,
            PlayerRole.role_id == role.id,
            PlayerRole.scope_type == scope_type
        )
        if scope_id:
            stmt = stmt.where(PlayerRole.scope_id == scope_id)
        role_to_remove = (await session.execute(stmt)).scalars().all()
        if len(role_to_remove) > 1:
            raise RoleServiceError("Bulk removal of roles not supported yet")

        return await self.delete_player_role(role_to_remove[0], actor=actor, session=session, audit_context=audit_context)
    
    # Delegated methods
    async def get_permission_by_name(self, *args, **kwargs):
        return await self.permission_service.get_permission_by_name(*args, **kwargs)
    
    async def get_all_permissions(self, *args, **kwargs):
        return await self.permission_service.get_all_permissions(*args, **kwargs)
    
    async def create_permission(self, *args, **kwargs):
        return await self.permission_service.create_permission(*args, **kwargs)
#######################################################################


def create_role_service(permission_svc: Optional[PermissionService] = None) -> RoleService:
    permission_service = permission_svc or PermissionService()
    return RoleService(permission_service)