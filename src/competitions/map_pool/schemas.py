
from typing import List
from datetime import datetime
from typing import Optional, Self

from pydantic import BaseModel, ConfigDict, model_validator, UUID4
from competitions.map_pool.models import MapPoolSelectionType, MapPoolStatus
from maps.schemas import MapBase


class MapPoolCreate(BaseModel):
    """Schema for creating a map pool"""
    selection_type: MapPoolSelectionType
    map_ids: Optional[List[UUID4]] = None  # For admin-defined pools
    voting_duration_days: Optional[int] = None  # For voting pools
    maps_to_select: Optional[int] = None  # Number of maps to select
    votes_per_team: Optional[int] = None  # Votes per team

    @model_validator(mode='after')
    def validate_selection_type_fields(self) -> Self:
        if self.selection_type == MapPoolSelectionType.ADMIN_DEFINED:
            if not self.map_ids:
                raise ValueError("map_ids required for admin-defined pools")
        elif self.selection_type == MapPoolSelectionType.TEAM_VOTING:
            if not all([self.voting_duration_days, self.maps_to_select, self.votes_per_team]):
                raise ValueError("voting_duration_days, maps_to_select, and votes_per_team required for voting pools")
        return self

class MapPoolVoteRequest(BaseModel):
    """Schema for voting on maps"""
    team_id: UUID4
    map_ids: List[UUID4]

    @model_validator(mode='after')
    def validate_vote_count(self) -> Self:
        if not self.map_ids:
            raise ValueError("At least one map must be selected")
        return self

class MapPoolVoteResponse(BaseModel):
    """Response schema for map voting"""
    team_id: UUID4
    maps_voted: List[UUID4]
    remaining_votes: int

class MapPoolResponse(BaseModel):
    """Response schema for map pool"""
    id: UUID4
    tournament_id: UUID4
    selection_type: MapPoolSelectionType
    status: MapPoolStatus
    maps: List[MapBase]
    voting_start: Optional[datetime]
    voting_end: Optional[datetime]
    maps_to_select: Optional[int]
    votes_per_team: Optional[int]
    created_at: datetime
    finalized_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)