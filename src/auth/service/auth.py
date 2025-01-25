from typing import List, Optional, Tuple, Dict
from sqlmodel.ext.asyncio.session import AsyncSession
import logging

from audit.context import AuditContext
from audit.schemas import AuditEventType
from audit.service import AuditService, create_audit_service
from auth.models import Player, Role
from auth.schemas import PlayerLogin, PlayerEmailCreate, TokenResponse, PlayerStatus,  AuthType, ScopeType
from auth.service.identity import IdentityService, create_identity_service
from auth.service.permission import PermissionService, create_permission_service
from auth.service.role import RoleService, create_role_service
from auth.service.status import PlayerStatusService
from auth.service.token import TokenConfig, TokenService, create_token_service
from config import Config
from status.service import StatusTransitionService, create_status_transition_service

LOG = logging.getLogger('uvicorn.error')

class AuthService:
    """Coordinates authentication and authorization flows"""
    
    def __init__(
        self,
        identity_service: IdentityService,
        token_service: TokenService,
        permission_service: PermissionService,
        role_service: RoleService,
        player_status_service: PlayerStatusService,
    ):
        self.identity_service = identity_service
        self.token_service = token_service
        self.permission_service = permission_service
        self.role_service = role_service
        self.player_status_service = player_status_service


    async def authenticate_player(
        self,
        login_data: PlayerLogin,
        session: AsyncSession
    ) -> Optional[Tuple[Player, TokenResponse]]:
        """Authenticate a player and return tokens if successful"""
        player = await self.identity_service.get_player_by_email(login_data.email, session)
        
        if not player or not self.identity_service.verify_password(
            login_data.password,
            player.password_hash
        ):
            return None
            
        # Check if player has access
        if not await self.check_player_access(player, session):
            return None
            
        tokens = self.token_service.create_auth_tokens(str(player.id), player.auth_type)
        return player, tokens
    
    # TODO - Add details extractor?
    @AuditService.audited_transaction(
            action_type=AuditEventType.CREATE,
            entity_type='Player',
    )
    async def create_player(
        self,
        player_data: PlayerEmailCreate,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Player:
        """Create a new player account with email"""
        # Create player
        player = await self.identity_service.create_player_with_email(
            player_data,
            actor=actor,
            session=session,
            audit_context=audit_context
        )
        
        # Assign default role
        user_role = await self.get_default_role(session)
        if not user_role:
            raise ValueError("Default user role not found")
            
        await self.assign_role(
            player=player,
            role=user_role,
            scope_type=ScopeType.GLOBAL,
            scope_id=None,
            actor=player,  # Self-registration
            session=session,
            audit_context=audit_context
        )
        await session.refresh(player)
        
        return player
    
    @AuditService.audited_transaction(
            action_type=AuditEventType.CREATE,
            entity_type='Player',
    )
    async def create_steam_player(
        self,
        steam_id: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> Player:
        """Create a new player account with Steam"""
        # Create player
        player = await self.identity_service.create_player_with_steam(
            steam_id,
            actor=actor,
            session=session,
            audit_context=audit_context
        )
        LOG.info(f"Player: {player}")
        # Assign default role
        user_role = await self.get_default_role(session)
        if not user_role:
            raise ValueError("Default user role not found")
        LOG.info(f"Player: {player} user_role {user_role}")
        await self.assign_role(
            player=player,
            role=user_role,
            scope_type=ScopeType.GLOBAL,
            scope_id=None,
            actor=player,  # Self-registration
            session=session,
            audit_context=audit_context
        )
        await session.refresh(player)
        
        return player

    async def refresh_auth_tokens(
        self,
        refresh_token: str,
        session: AsyncSession
    ) -> Optional[TokenResponse]:
        """Get new tokens using refresh token"""
        token_data = self.token_service.verify_token(refresh_token)
        if not token_data or not token_data.get('is_refresh'):
            return None
            
        # Verify player still has access
        player = await self.identity_service.get_player_by_id(
            token_data['player_id'],
            session
        )
        if not player or not await self.check_player_access(player, session):
            return None
            
        return self.token_service.create_auth_tokens(
            token_data['player_id'],
            AuthType(token_data['auth_type'])
        )

    async def get_default_role(self, session: AsyncSession) -> Optional[Role]:
        """Get the default role for new players"""
        # This could be cached or configured elsewhere
        return await self.role_service.get_role_by_name("user", session)

    # Identity Service delegations
    async def get_all_players(self, *args, **kwargs):
        return await self.identity_service.get_all_players(*args, **kwargs)

    async def get_all_players_with_basic_team_info(self, *args, **kwargs):
        return await self.identity_service.get_all_players_with_basic_team_info(*args, **kwargs)

    async def get_player_by_id(self, *args, **kwargs):
        return await self.identity_service.get_player_by_id(*args, **kwargs)
    
    async def get_player_by_name(self, *args, **kwargs):
        return await self.identity_service.get_player_by_name(*args, **kwargs)

    async def get_player_by_email(self, *args, **kwargs):
        return await self.identity_service.get_player_by_email(*args, **kwargs)

    async def get_player_by_steam_id(self, *args, **kwargs):
        return await self.identity_service.get_player_by_steam_id(*args, **kwargs)

    async def create_player_with_email(self, *args, **kwargs):
        return await self.identity_service.create_player_with_email(*args, **kwargs)

    async def create_player_with_steam(self, *args, **kwargs):
        return await self.identity_service.create_player_with_steam(*args, **kwargs)

    # Token Service delegations  
    def create_token(self, *args, **kwargs):
        return self.token_service.create_token(*args, **kwargs)

    def verify_token(self, *args, **kwargs):
        return self.token_service.verify_token(*args, **kwargs)

    def create_auth_tokens(self, *args, **kwargs):
        return self.token_service.create_auth_tokens(*args, **kwargs)
    
    def refresh_access_token(self, *args, **kwargs):
          return self.token_service.refresh_access_token(self, *args, **kwargs)

    # Permission Service delegations
    async def verify_permissions(self, *args, **kwargs):
        return await self.permission_service.verify_permissions(*args, **kwargs)
    
    async def get_permission(self, *args, **kwargs):
        return await self.permission_service.get_permission(*args, **kwargs)

    async def get_permission_by_name(self, *args, **kwargs):
        return await self.permission_service.get_permission_by_name(*args, **kwargs)

    async def get_all_permissions(self, *args, **kwargs):
        return await self.permission_service.get_all_permissions(*args, **kwargs)

    async def create_permission(self, *args, **kwargs):
        return await self.permission_service.create_permission(*args, **kwargs)

    async def delete_permission(self, *args, **kwargs):
        return await self.permission_service.delete_permission(*args, **kwargs)


    # Role Service delegations
    async def verify_role(self, *args, **kwargs):
        return await self.role_service.verify_role(*args, **kwargs)

    async def assign_role(self, *args, **kwargs):
        return await self.role_service.assign_role(*args, **kwargs)
    
    async def get_player_roles(self, *args, **kwargs):
        return await self.role_service.get_player_roles(*args, **kwargs)
    
    async def get_all_roles(self, *args, **kwargs):
        return await self.role_service.get_all_roles(*args, **kwargs)

    async def get_role_by_name(self, *args, **kwargs):
        return await self.role_service.get_role_by_name(*args, **kwargs)
        
    async def create_role(self, *args, **kwargs):
        return await self.role_service.create_role(*args, **kwargs)
    
    async def delete_role(self, *args, **kwargs):
        return await self.role_service.delete_role(*args, **kwargs)
    
    async def remove_role_from_player(self, *args, **kwargs):
        return await self.role_service.remove_role_from_player(*args, **kwargs)
    
    async def update_role(self, *args, **kwargs):
        return await self.role_service.update_role(*args, **kwargs)
    
    # Status Service delegations  
    async def change_player_status(self, *args, **kwargs):
        return await self.player_status_service.change_player_status(*args, **kwargs)
        
    async def check_player_access(self, *args, **kwargs):
        return await self.player_status_service.check_player_access(*args, **kwargs)

    async def get_player_status_history(self, *args, **kwargs):
        return await self.player_status_service.get_player_status_history(*args, **kwargs)
        
    async def reactivate_player(self, *args, **kwargs):
        return await self.player_status_service.reactivate_player(*args, **kwargs)
        
    async def suspend_player(self, *args, **kwargs):
        return await self.player_status_service.suspend_player(*args, **kwargs)
        
    async def soft_delete_player(self, *args, **kwargs):
        return await self.player_status_service.soft_delete_player(*args, **kwargs)

# Create AuthService instance
def create_auth_service(
        identity_svc: Optional[IdentityService] = None,
        token_service: Optional[TokenService] = None,
        audit_svc: Optional[AuditService] = None,
        permission_service: Optional[PermissionService] = None,
        role_service: Optional[RoleService] = None,
        status_transition_service: Optional[StatusTransitionService] = None,
        player_status_service: Optional[PlayerStatusService] = None
        
        
        
        
        ) -> AuthService:
    """Create and configure the AuthService with its dependencies"""

    # Create service instances
    identity_service = identity_svc or create_identity_service()
    token_service = token_service or create_token_service()
    audit_service = audit_svc or create_audit_service()
    permission_service = permission_service or create_permission_service(audit_service)
    role_service = role_service or create_role_service(permission_service)
    status_transition_service = status_transition_service or create_status_transition_service(audit_service, permission_service)
    player_status_service = PlayerStatusService(identity_service, status_transition_service)

    # Create and return AuthService
    return AuthService(
        identity_service=identity_service,
        token_service=token_service,
        permission_service=permission_service,
        role_service=role_service,
        player_status_service=player_status_service
    )