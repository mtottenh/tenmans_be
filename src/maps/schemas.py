from pydantic import BaseModel, UUID4, ConfigDict, Field, HttpUrl
from typing import List, Optional, Dict, Any
from datetime import datetime

# Map Schemas
class MapCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    img: str

class MapCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    map_img_token_id: str

# class MapUpdate(BaseModel):
#     name: Optional[str] = Field(None, min_length=2, max_length=50)
#     img_url: Optional[HttpUrl]

class MapBase(BaseModel):
    id: UUID4
    name: str
    img: str
    # created_at: datetime
    # updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MapDetailed(MapBase):
    times_played: int
    t_side_win_percentage: float
    ct_side_win_percentage: float
    average_round_time: float  # in seconds
    most_recent_match: datetime

class TournamentMapPool(BaseModel):
    tournament_id: UUID4
    maps: List[MapBase]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Map Statistics Schemas
class MapStatistics(BaseModel):
    map_id: UUID4
    total_matches: int
    total_rounds: int
    t_rounds_won: int
    ct_rounds_won: int
    average_match_duration: float  # in minutes
    most_common_final_score: str
    longest_match_duration: float  # in minutes
    shortest_match_duration: float  # in minutes

    model_config = ConfigDict(from_attributes=True)

class MapTournamentStatistics(MapStatistics):
    tournament_id: UUID4
    tournament_name: str
    matches_in_tournament: int
    percentage_of_tournament_matches: float

        
