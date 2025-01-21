from pydantic import BaseModel, UUID4, ConfigDict, Field, computed_field
from typing import List, Optional
from datetime import datetime
from teams.base_schemas import RosterStatus, TeamBase, TeamCaptainStatus, TeamHistory
from auth.schemas import PlayerPublic


# Response Schemas
class RosterMember(BaseModel):
    player: PlayerPublic
    status: RosterStatus
    created_at: datetime
    updated_at: datetime
    season_id: UUID4
    model_config = ConfigDict(from_attributes=True)

class TeamCaptainInfo(BaseModel):
    id: UUID4
    player: PlayerPublic
    status: TeamCaptainStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TeamDetailed(TeamBase):
    rosters: List[RosterMember]
    captains: List[TeamCaptainInfo]
    max_roster_size: int = Field(default=99) 
    #current_elo_history: Optional[TeamELOHistory]
    @computed_field
    @property
    def active_roster_count(self) ->int:
        return len([x for x in self.rosters if  x.status == RosterStatus.ACTIVE])
    
class PlayerRosterHistory(BaseModel):
    current: Optional[TeamHistory]
    previous: Optional[List[TeamHistory]]
