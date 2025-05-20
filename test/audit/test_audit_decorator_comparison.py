import uuid
from typing import Optional
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel

from audit.context import AuditContext
from audit.models import AuditEvent
from audit.schemas import AuditEventType
from audit.service import AuditService
from auth.models import Player


# Create test entities
class AuditTeamModel(SQLModel, table=True):
    """A simplified Team model for testing"""

    __tablename__ = "test_audit_teams"

    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str
    status: str = Field(default="ACTIVE")


class AuditTournamentModel(SQLModel, table=True):
    """A simplified Tournament model for testing"""

    __tablename__ = "test_audit_tournaments"

    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str
    status: str = Field(default="NOT_STARTED")


class ComparisonTestService:
    """Service to demonstrate the difference between default and entity_param behavior"""

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TestEntity",
        # No entity_param specified - will use first SQLModel entity
    )
    async def register_team_default(
        self,
        team: AuditTeamModel,  # This comes first
        tournament: AuditTournamentModel,  # This is what we actually want to audit
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> None:
        """Register a team for a tournament using default behavior"""
        # In reality, this would create a TournamentRegistration
        # For this test, we'll just update the tournament state
        tournament.status = "REGISTRATION_OPEN"
        session.add(tournament)
        await session.flush()

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TestEntity",
        entity_param="tournament",  # Explicitly specify which parameter to audit
    )
    async def register_team_with_param(
        self,
        team: AuditTeamModel,  # This comes first
        tournament: AuditTournamentModel,  # This is what we actually want to audit
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
    ) -> None:
        """Register a team for a tournament with entity_param specified"""
        # Same logic as above
        tournament.status = "REGISTRATION_OPEN"
        session.add(tournament)
        await session.flush()


class TestEntityParamComparison:
    """Test to show the difference between default behavior and entity_param"""

    @pytest_asyncio.fixture
    async def setup_data(self, session: AsyncSession):
        """Create test data"""
        team = AuditTeamModel(name="Test Team")
        tournament = AuditTournamentModel(name="Test Tournament")

        session.add(team)
        session.add(tournament)
        await session.commit()
        await session.refresh(team)
        await session.refresh(tournament)

        return {"team": team, "tournament": tournament}

    @pytest.mark.asyncio
    async def test_default_behavior_audits_wrong_entity(
        self, setup_data, session: AsyncSession, system_user: Player
    ):
        """Test that default behavior audits the first SQLModel entity (team)"""
        service = ComparisonTestService()
        team = setup_data["team"]
        tournament = setup_data["tournament"]

        # Call the method without entity_param
        await service.register_team_default(team, tournament, system_user, session)

        # Check audit events for the team (wrong entity!)
        team_events = await session.execute(
            AuditEvent.__table__.select().where(AuditEvent.entity_id == team.id)
        )
        team_audit_events = team_events.fetchall()

        # The audit event was created for the team, not the tournament!
        assert len(team_audit_events) > 0
        latest_team_event = max(team_audit_events, key=lambda e: e.timestamp)
        assert latest_team_event.entity_type == "TestEntity"  # Wrong entity type!
        assert latest_team_event.entity_id == team.id  # This is the team ID!

        # Check audit events for the tournament
        tournament_events = await session.execute(
            AuditEvent.__table__.select().where(AuditEvent.entity_id == tournament.id)
        )
        tournament_audit_events = tournament_events.fetchall()

        # No audit event for the tournament (which is what we wanted to audit)
        assert len(tournament_audit_events) == 0

    @pytest.mark.asyncio
    async def test_entity_param_audits_correct_entity(
        self, setup_data, session: AsyncSession, system_user: Player
    ):
        """Test that entity_param correctly identifies the tournament to audit"""
        service = ComparisonTestService()
        team = setup_data["team"]
        tournament = setup_data["tournament"]

        # Call the method with entity_param="tournament"
        await service.register_team_with_param(team, tournament, system_user, session)

        # Check audit events for the tournament (correct entity!)
        tournament_events = await session.execute(
            AuditEvent.__table__.select().where(AuditEvent.entity_id == tournament.id)
        )
        tournament_audit_events = tournament_events.fetchall()

        # The audit event was created for the tournament correctly
        assert len(tournament_audit_events) > 0
        latest_tournament_event = max(
            tournament_audit_events, key=lambda e: e.timestamp
        )
        assert latest_tournament_event.entity_type == "TestEntity"
        assert latest_tournament_event.entity_id == tournament.id  # Correct!

        # Check audit events for the team
        team_events = await session.execute(
            AuditEvent.__table__.select().where(AuditEvent.entity_id == team.id)
        )
        team_audit_events = team_events.fetchall()

        # No audit event for the team (which is correct)
        # Note: In the first test, the team had an audit event from the default behavior
        assert len([e for e in team_audit_events if e.entity_type == "TestEntity"]) == 0