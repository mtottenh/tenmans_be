from sqlmodel import SQLModel, Field, Column, Relationship, select
import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from enum import StrEnum
from typing import List, Optional
import uuid
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import AsyncAttrs

from matches.models import MatchFormat, Result
from matches.schemas import ConfirmationStatus
class FixtureStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FORFEITED = "forfeited"

class Fixture(SQLModel, AsyncAttrs, table=True):
    __tablename__ = "fixtures"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4))
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    round_id: uuid.UUID = Field(sa_column=Column(ForeignKey("rounds.id")))
    team_1: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    team_2: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    match_format: str  # bo1, bo3, bo5
    scheduled_at: datetime
    rescheduled_from: Optional[datetime]
    rescheduled_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.uid")))
    reschedule_reason: Optional[str]
    status: FixtureStatus = Field(sa_column=sa.Column(sa.Enum(FixtureStatus)))
    forfeit_winner: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("teams.id")))
    forfeit_reason: Optional[str]
    admin_notes: Optional[str]
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    tournament: "Tournament" = Relationship(back_populates="fixtures")
    round: "Round" = Relationship(back_populates="fixtures")
    team_1_rel: "Team" = Relationship(
        back_populates="home_fixtures",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_1"}
    )
    team_2_rel: "Team" = Relationship(
        back_populates="away_fixtures",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_2"}
    )
    results: List["Result"] = Relationship(back_populates="fixture")
    match_players: List["MatchPlayer"] = Relationship(back_populates="fixture")
    #team_elo_changes: List["TeamELOHistory"] = Relationship(back_populates="fixture")


    @property
    def maps_completed(self) -> int:
        """Number of completed maps"""
        return len([r for r in self.results if r.confirmation_status == ConfirmationStatus.CONFIRMED])
    
    @property
    def maps_needed(self) -> int:
        """Maps needed to win based on format"""
        format_maps = {
            MatchFormat.BO1: 1,
            MatchFormat.BO3: 2,
            MatchFormat.BO5: 3
        }
        return format_maps[self.match_format]
    
    async def get_winner_id(self, session: AsyncSession) -> Optional[uuid.UUID]:
        """Get winner ID if match is complete"""
        if self.status == FixtureStatus.FORFEITED:
            return self.forfeit_winner
            
        if self.status != FixtureStatus.COMPLETED:
            return None
            
        stmt = select(Result).where(Result.fixture_id == self.id)
        results = (await session.execute(stmt)).scalars().all()
        
        team_1_wins = sum(1 for r in results 
                        if r.confirmation_status == ConfirmationStatus.CONFIRMED 
                        and r.team_1_score > r.team_2_score)
                        
        team_2_wins = sum(1 for r in results
                        if r.confirmation_status == ConfirmationStatus.CONFIRMED 
                        and r.team_2_score > r.team_1_score)
                        
        if team_1_wins >= self.maps_needed:
            return self.team_1
        elif team_2_wins >= self.maps_needed: 
            return self.team_2
            
        return None

    @property 
    async def can_complete(self) -> bool:
        """Check if fixture has enough confirmed results to complete"""
        if self.status != FixtureStatus.IN_PROGRESS:
            return False
            
        team_1_wins = 0
        team_2_wins = 0
        
        for result in self.results:
            if result.confirmation_status != ConfirmationStatus.CONFIRMED:
                continue
            if result.winner_id == self.team_1:
                team_1_wins += 1
            elif result.winner_id == self.team_2:
                team_2_wins += 1
                
        return team_1_wins >= self.maps_needed or team_2_wins >= self.maps_needed