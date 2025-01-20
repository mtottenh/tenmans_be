from typing import List, Dict, Optional
from datetime import datetime
from sqlmodel.ext.asyncio.session import AsyncSession
import uuid

from audit.service import AuditService, create_audit_service
from auth.models import Player
from auth.schemas import PlayerStatus
from auth.service.identity import IdentityService, create_identity_service
from auth.service.permission import PermissionService, create_permission_service
from status.service import StatusTransitionService, create_status_transition_service
from status.manager.player import initialize_player_status_manager

class PlayerStatusService:
    """Service for managing player status transitions and history"""
    
    def __init__(self, identity_service: IdentityService, status_transition_service: StatusTransitionService):
        self.identity_service = identity_service
        self.status_transition_service = status_transition_service
        
        # Register player status transition manager
        player_manager = initialize_player_status_manager()
        self.status_transition_service.register_transition_manager('Player', player_manager)

    async def change_player_status(
        self,
        player_id: uuid.UUID,
        new_status: str,
        reason: str,
        actor: Player,
        entity_metadata: Optional[Dict] = None,
        session: AsyncSession = None
    ) -> Player:
        """
        Change a player's status with validation and history tracking
        
        Args:
            player_id: Player's UUID
            new_status: New status to set
            reason: Reason for the change
            actor: User making the change
            entity_metadata: Additional entity_metadata
            session: Database session
        """
        player = await self.identity_service.get_player_by_id(player_id, session)
        if not player:
            raise ValueError(f"Player {player_id} not found")
            
        # Use status transition service to handle the change
        updated_player = await self.status_transition_service.transition_status(
            entity=player,
            new_status=new_status,
            reason=reason,
            actor=actor,
            entity_metadata=entity_metadata,
            session=session
        )
        
        return updated_player

    async def get_player_status_history(
        self,
        player_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Dict]:
        """Get status change history for a player"""
        player = await self.identity_service.get_player_by_id(player_id, session)
        if not player:
            raise ValueError(f"Player {player_id} not found")
            
        return await self.status_transition_service.get_status_history(
            entity_type="Player",
            entity_id=player_id,
            session=session
        )

    async def reactivate_player(
        self,
        player_id: uuid.UUID,
        reason: str,
        actor: Player,
        session: AsyncSession
    ) -> Player:
        """Helper method to reactivate a player"""
        return await self.change_player_status(
            player_id=player_id,
            new_status=PlayerStatus.ACTIVE,
            reason=reason,
            actor=actor,
            session=session
        )

    async def suspend_player(
        self,
        player_id: uuid.UUID,
        reason: str,
        end_date: datetime,
        actor: Player,
        session: AsyncSession
    ) -> Player:
        """Helper method to suspend a player"""
        entity_metadata = {"suspension_end": end_date.isoformat()}
        return await self.change_player_status(
            player_id=player_id,
            new_status=PlayerStatus.SUSPENDED,
            reason=reason,
            actor=actor,
            entity_metadata=entity_metadata,
            session=session
        )

    async def soft_delete_player(
        self,
        player_id: uuid.UUID,
        reason: str,
        actor: Player,
        session: AsyncSession
    ) -> Player:
        """Helper method to soft delete a player"""
        return await self.change_player_status(
            player_id=player_id,
            new_status=PlayerStatus.DELETED,
            reason=reason,
            actor=actor,
            session=session
        )

    async def check_player_access(
        self,
        player: Player,
        session: AsyncSession
    ) -> bool:
        """
        Check if a player has access to the system
        Returns False if player is suspended, banned, deleted, etc.
        """
        if not player:
            return False
            
        return player.status == PlayerStatus.ACTIVE
    

def create_player_status_service(identity_service: Optional[IdentityService] = None,
                                 audit_service: Optional[AuditService] = None,
                                 permission_service: Optional[PermissionService] = None,
                                 status_transition_service: Optional[StatusTransitionService] = None) -> PlayerStatusService:
    identity_service = identity_service or create_identity_service()
    audit_service = audit_service or create_audit_service()
    permission_service = permission_service or create_permission_service(audit_service)
    status_transition_service = status_transition_service or create_status_transition_service(audit_service, permission_service)
    return PlayerStatusService(identity_service, status_transition_service)