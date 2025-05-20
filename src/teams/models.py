import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Column, Field, Relationship, SQLModel

from db.models import created_at_field, timestamp_column, updated_at_field

from competitions.models.lobby import MapVetoAction, MapVetoSession
from competitions.models.scheduling import TeamAvailability
from competitions.models.seasons import Season
from matches.evidence.models import EvidenceConfirmation
from teams.base_schemas import (
    RecruitmentStatus,
    RosterStatus,
    TeamCaptainStatus,
    TeamStatus,
)


if TYPE_CHECKING:
    from auth.models import Player
    from competitions.map_pool.models import MapPoolVote
    from competitions.models.fixtures import Fixture
    from competitions.models.tournaments import TournamentRegistration
    from matches.models import MatchPlayer
    from moderation.models import Ban
    from teams.join_request.models import TeamJoinRequest


class Team(SQLModel, table=True):
    __tablename__ = "teams"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    name: str = Field(unique=True)
    status: TeamStatus = Field(default=TeamStatus.ACTIVE)
    disbanded_at: Optional[datetime] = None
    disbanded_reason: Optional[str] = None
    disbanded_by: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("players.id"))
    )
    logo: Optional[str]
    recruitment_status: RecruitmentStatus = Field(default=RecruitmentStatus.ACTIVE)
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    # Existing relationships
    rosters: list["Roster"] = Relationship(back_populates="team")
    captains: list["TeamCaptain"] = Relationship(back_populates="team")
    home_fixtures: list["Fixture"] = Relationship(
        back_populates="team_1_rel",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_1"},
    )
    away_fixtures: list["Fixture"] = Relationship(
        back_populates="team_2_rel",
        sa_relationship_kwargs={"foreign_keys": "Fixture.team_2"},
    )
    bans: list["Ban"] = Relationship(back_populates="team")
    join_requests: list["TeamJoinRequest"] = Relationship(back_populates="team")
    tournament_registrations: list["TournamentRegistration"] = Relationship(
        back_populates="team"
    )
    match_players: list["MatchPlayer"] = Relationship(back_populates="team")

    # New relationships for the enhanced features
    map_votes: list["MapPoolVote"] = Relationship(back_populates="team")
    availability: list["TeamAvailability"] = Relationship(back_populates="team")
    evidence_confirmations: list[EvidenceConfirmation] = Relationship(
        back_populates="team"
    )
    veto_sessions: list[MapVetoSession] = Relationship(
        back_populates="current_team",
        sa_relationship_kwargs={"foreign_keys": "[MapVetoSession.current_team_id]"},
    )
    veto_actions: list[MapVetoAction] = Relationship(back_populates="team")


class Roster(SQLModel, table=True):
    __tablename__ = "rosters"
    team_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("teams.id"), primary_key=True)
    )
    player_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("players.id"), primary_key=True)
    )
    season_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("seasons.id"), primary_key=True)
    )
    status: RosterStatus = Field(default=RosterStatus.PENDING)
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    team: Team = Relationship(back_populates="rosters")
    player: "Player" = Relationship(back_populates="team_rosters")
    season: Season = Relationship(back_populates="rosters")


class TeamCaptain(SQLModel, table=True):
    __tablename__ = "team_captains"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )

    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    player_id: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))

    status: TeamCaptainStatus = Field(default=TeamCaptainStatus.ACTIVE)
    created_at: datetime = created_at_field()

    team: Team = Relationship(back_populates="captains")
    player: "Player" = Relationship(back_populates="captain_of")


# class TeamELOHistory(SQLModel, table=True):
#     __tablename__ = "team_elo_history"
#     id: uuid.UUID = Field(
#         sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4))

#     team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
#     fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
#     elo_rating: int
#     player_composition: List[uuid.UUID] = Field(sa_column=Column(JSON))
#     created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

#     team: Team = Relationship(back_populates="elo_history")
#     fixture: "Fixture" = Relationship(back_populates="team_elo_changes")
