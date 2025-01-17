from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from .models import (
    TournamentMapPool, 
    MapPoolMap, 
    MapPoolVote,
    MapPoolSelectionType,
    MapPoolStatus
)
from src.maps.models import Map
from src.teams.models import Team

class MapPoolError(Exception):
    """Base exception for map pool operations"""
    pass

class MapPoolService:
    async def create_admin_map_pool(
        self,
        tournament_id: uuid.UUID,
        map_ids: List[uuid.UUID],
        session: AsyncSession
    ) -> TournamentMapPool:
        """Create an admin-defined map pool"""
        # Verify all maps exist
        for map_id in map_ids:
            map_exists = await session.get(Map, map_id)
            if not map_exists:
                raise MapPoolError(f"Map {map_id} not found")
        
        # Create the map pool
        map_pool = TournamentMapPool(
            tournament_id=tournament_id,
            selection_type=MapPoolSelectionType.ADMIN_DEFINED,
            status=MapPoolStatus.FINALIZED,
            finalized_at=datetime.now()
        )
        session.add(map_pool)
        await session.flush()  # Get the pool ID
        
        # Add maps to the pool
        pool_maps = [
            MapPoolMap(pool_id=map_pool.id, map_id=map_id)
            for map_id in map_ids
        ]
        session.add_all(pool_maps)
        await session.commit()
        await session.refresh(map_pool)
        
        return map_pool

    async def create_voting_pool(
        self,
        tournament_id: uuid.UUID,
        voting_duration: timedelta,
        maps_to_select: int,
        votes_per_team: int,
        session: AsyncSession
    ) -> TournamentMapPool:
        """Create a team voting-based map pool"""
        voting_start = datetime.now()
        voting_end = voting_start + voting_duration
        
        map_pool = TournamentMapPool(
            tournament_id=tournament_id,
            selection_type=MapPoolSelectionType.TEAM_VOTING,
            status=MapPoolStatus.VOTING,
            voting_start=voting_start,
            voting_end=voting_end,
            maps_to_select=maps_to_select,
            votes_per_team=votes_per_team
        )
        
        session.add(map_pool)
        await session.commit()
        await session.refresh(map_pool)
        
        return map_pool

    async def cast_team_vote(
        self,
        pool_id: uuid.UUID,
        team_id: uuid.UUID,
        map_id: uuid.UUID,
        session: AsyncSession
    ) -> MapPoolVote:
        """Record a team's vote for a map"""
        # Get the map pool and verify voting is open
        map_pool = await session.get(TournamentMapPool, pool_id)
        if not map_pool:
            raise MapPoolError("Map pool not found")
            
        if map_pool.status != MapPoolStatus.VOTING:
            raise MapPoolError("Voting is not currently open")
            
        if datetime.now() > map_pool.voting_end:
            raise MapPoolError("Voting period has ended")
            
        # Check if team has remaining votes
        stmt = select(MapPoolVote).where(
            MapPoolVote.pool_id == pool_id,
            MapPoolVote.team_id == team_id
        )
        result = (await session.execute(stmt)).scalars()
        existing_votes = result.all()
        
        if len(existing_votes) >= map_pool.votes_per_team:
            raise MapPoolError("Team has used all available votes")
            
        # Record the vote
        vote = MapPoolVote(
            pool_id=pool_id,
            team_id=team_id,
            map_id=map_id
        )
        session.add(vote)
        
        # Update vote count in map_pool_maps
        stmt = select(MapPoolMap).where(
            MapPoolMap.pool_id == pool_id,
            MapPoolMap.map_id == map_id
        )
        result = (await session.execute(stmt)).scalars()
        pool_map = result.first()
        
        if pool_map:
            pool_map.vote_count = (pool_map.vote_count or 0) + 1
            session.add(pool_map)
        
        await session.commit()
        await session.refresh(vote)
        
        return vote

    async def finalize_voting_pool(
        self,
        pool_id: uuid.UUID,
        session: AsyncSession
    ) -> TournamentMapPool:
        """Finalize a voting-based map pool"""
        map_pool = await session.get(TournamentMapPool, pool_id)
        if not map_pool:
            raise MapPoolError("Map pool not found")
            
        if map_pool.status != MapPoolStatus.VOTING:
            raise MapPoolError("Map pool is not in voting status")
            
        if datetime.now() < map_pool.voting_end:
            raise MapPoolError("Voting period has not ended")
            
        # Get maps ordered by vote count
        stmt = select(MapPoolMap).where(
            MapPoolMap.pool_id == pool_id
        ).order_by(MapPoolMap.vote_count.desc())
        result = (await session.execute(stmt)).scalars()
        maps = result.all()
        
        # Select top N maps
        selected_maps = maps[:map_pool.maps_to_select]
        
        # Remove maps that weren't selected
        for map in maps[map_pool.maps_to_select:]:
            await session.delete(map)
            
        # Update map pool status
        map_pool.status = MapPoolStatus.FINALIZED
        map_pool.finalized_at = datetime.now()
        
        await session.commit()
        await session.refresh(map_pool)
        
        return map_pool

    async def get_pool_status(
        self,
        pool_id: uuid.UUID,
        session: AsyncSession
    ) -> dict:
        """Get current status of a map pool"""
        map_pool = await session.get(TournamentMapPool, pool_id)
        if not map_pool:
            raise MapPoolError("Map pool not found")
            
        # Get maps and votes if this is a voting pool
        maps_data = []
        if map_pool.selection_type == MapPoolSelectionType.TEAM_VOTING:
            stmt = select(MapPoolMap, Map).join(Map).where(
                MapPoolMap.pool_id == pool_id
            ).order_by(MapPoolMap.vote_count.desc())
            result = (await session.execute(stmt)).scalars()
            maps_data = [
                {
                    "map_id": str(map.id),
                    "name": map.name,
                    "votes": pool_map.vote_count or 0
                }
                for pool_map, map in result
            ]
        
        return {
            "id": str(map_pool.id),
            "status": map_pool.status,
            "selection_type": map_pool.selection_type,
            "voting_end": map_pool.voting_end,
            "maps_to_select": map_pool.maps_to_select,
            "maps": maps_data
        }