# status/transition_steps/map_pool.py

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from competitions.map_pool.models import MapPoolSelectionType, TournamentMapPool, MapPoolStatus, MapPoolMap
from status.pipeline import TransitionStep

LOG = logging.getLogger('uvicorn.error')

class MapPoolVotingCompleteStep(TransitionStep):
    """Pipeline step to finalize map pool when voting ends"""
    
    async def execute(
        self,
        entity: TournamentMapPool,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != MapPoolStatus.FINALIZED.value:
            return  # Only act on finalization
        
        if entity.selection_type != MapPoolSelectionType.TEAM_VOTING:
            return  # Only relevant for voting pools
        
        # Get all map votes ordered by count
        stmt = select(MapPoolMap).where(
            MapPoolMap.pool_id == entity.id
        ).order_by(MapPoolMap.vote_count.desc())
        result = await session.execute(stmt)
        all_maps: List[MapPoolMap]= result.scalars().all()
        
        # Keep only the top N maps
        selected_maps = all_maps[:entity.maps_to_select]
        unselected_maps = all_maps[entity.maps_to_select:]
        
        LOG.info(f"Finalizing map pool {entity.id} with {len(selected_maps)} selected maps")
        
        # Remove unselected maps
        for pool_map in unselected_maps:
            LOG.info(f"Removing unselected map {pool_map.map_id} with {pool_map.vote_count} votes")
            await session.delete(pool_map)

class MapPoolNotificationStep(TransitionStep):
    """Pipeline step to notify teams when map pool is finalized"""
    
    async def execute(
        self,
        entity: TournamentMapPool,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != MapPoolStatus.FINALIZED.value:
            return  # Only act on finalization
        
        # TODO: Implement notification system
        # For now, just log the notification
        LOG.info(f"Map pool {entity.id} finalized for tournament {entity.tournament_id}")