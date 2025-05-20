import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import selectinload
from sqlmodel import Column, Field, Relationship, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from competitions.models.scheduling import ScheduleConflict, ScheduleSuggestion
from db.models import enum_column, created_at_field, updated_at_field, timestamp_column
from matches.models import MatchFormat, Result
from matches.schemas import ConfirmationStatus


if TYPE_CHECKING:
    from competitions.models.lobby import MapVetoSession
    from competitions.models.rounds import Round
    from competitions.models.tournaments import Tournament
    from matches.evidence.models import MatchEvidence
    from matches.models import MatchPlayer
    from teams.models import Team



class FixtureStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FORFEITED = "forfeited"


class Fixture(SQLModel, table=True):
    __tablename__ = "fixtures"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    tournament_id: uuid.UUID = Field(sa_column=Column(ForeignKey("tournaments.id")))
    round_id: uuid.UUID = Field(sa_column=Column(ForeignKey("rounds.id")))
    team_1: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    team_2: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    match_format: str  # bo1, bo3, bo5
    scheduled_at: datetime = Field(sa_column=timestamp_column())
    rescheduled_from: Optional[datetime] = Field(sa_column=timestamp_column(nullable=True))
    rescheduled_by: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("players.id"))
    )
    reschedule_reason: Optional[str]
    status: FixtureStatus = Field(sa_column=enum_column(FixtureStatus))
    forfeit_winner: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("teams.id"))
    )
    forfeit_reason: Optional[str]
    admin_notes: Optional[str]
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    # Existing relationships
    tournament: "Tournament" = Relationship(back_populates="fixtures")
    round: "Round" = Relationship(back_populates="fixtures")
    team_1_rel: "Team" = Relationship(
        back_populates="home_fixtures",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_1"},
    )
    team_2_rel: "Team" = Relationship(
        back_populates="away_fixtures",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_2"},
    )
    results: list["Result"] = Relationship(back_populates="fixture")
    match_players: list["MatchPlayer"] = Relationship(back_populates="fixture")

    # New relationships for enhanced features
    schedule_suggestions: list["ScheduleSuggestion"] = Relationship(
        back_populates="fixture"
    )
    schedule_conflicts: list["ScheduleConflict"] = Relationship(
        back_populates="fixture"
    )
    evidence: list["MatchEvidence"] = Relationship(back_populates="fixture")
    veto_session: Optional["MapVetoSession"] = Relationship(back_populates="fixture")

    @property
    def maps_completed(self) -> int:
        """Number of completed maps"""
        return len(
            [
                r
                for r in self.results
                if r.confirmation_status == ConfirmationStatus.CONFIRMED
            ]
        )

    @property
    def maps_needed(self) -> int:
        """Maps needed to win based on format"""
        format_maps = {MatchFormat.BO1: 1, MatchFormat.BO3: 2, MatchFormat.BO5: 3}
        return format_maps[self.match_format]

    def get_winner_id_sync(self) -> Optional[uuid.UUID]:
        """Synchronous method to get winner if fixture is forfeited"""
        if self.status == FixtureStatus.FORFEITED:
            return self.forfeit_winner
        return None

    async def get_winner_id(self, session: AsyncSession) -> Optional[uuid.UUID]:
        """Get winner ID if match is complete"""
        # First check if it's a forfeit (no DB query needed)
        forfeit_winner = self.get_winner_id_sync()
        if forfeit_winner:
            return forfeit_winner

        if self.status != FixtureStatus.COMPLETED:
            return None

        # Load results with selectinload if they're not already loaded
        if not hasattr(self, "_results_loaded"):
            stmt = (
                select(Fixture)
                .where(Fixture.id == self.id)
                .options(selectinload(Fixture.results))
            )
            fixture_with_results = (await session.execute(stmt)).scalar_one_or_none()
            if fixture_with_results:
                self.results = fixture_with_results.results
                self._results_loaded = True

        team_1_wins = sum(
            1
            for r in self.results
            if r.confirmation_status == ConfirmationStatus.CONFIRMED
            and r.team_1_score > r.team_2_score
        )

        team_2_wins = sum(
            1
            for r in self.results
            if r.confirmation_status == ConfirmationStatus.CONFIRMED
            and r.team_2_score > r.team_1_score
        )

        if team_1_wins >= self.maps_needed:
            return self.team_1
        elif team_2_wins >= self.maps_needed:
            return self.team_2

        return None

    def can_complete_sync(self) -> bool:
        """Synchronous check if fixture can be completed based on results"""
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
