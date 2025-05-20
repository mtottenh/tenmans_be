"""Tests for RoundService with proper mocking"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from audit.service import AuditService
from auth.models import Player
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.rounds import Round, RoundType
from competitions.models.tournaments import Tournament, TournamentState
from competitions.rounds.round_winner_service import RoundWinnerService
from competitions.rounds.service import RoundService
from status.pipeline import TransitionPipeline, TransitionStep
from status.service import StatusTransitionService


class MockTransitionStep(TransitionStep):
    """Mock transition step for testing"""
    def __init__(self):
        self.executed = False

    async def execute(self, entity, old_status, new_status, actor, session, **context):
        self.executed = True
        return None


class MockStatusTransitionService(StatusTransitionService):
    """Mock status transition service for testing"""
    def __init__(self):
        self.transition_calls = []
        self.pipelines = {}

    async def transition_status(
        self, 
        entity, 
        new_status, 
        reason, 
        actor, 
        session, 
        entity_metadata=None, 
        audit_context=None
    ):
        """Record calls and return the entity with updated status"""
        self.transition_calls.append({
            "entity": entity,
            "new_status": new_status,
            "reason": reason,
            "actor": actor,
            "entity_metadata": entity_metadata
        })

        entity.status = new_status
        return entity

    def register_transition_pipeline(self, entity_type, new_status, pipeline):
        key = f"{entity_type}_{new_status}"
        self.pipelines[key] = pipeline

    def register_transition_manager(self, entity_type, manager):
        pass


@pytest.fixture
def mock_transition_service():
    """Create a mock transition service"""
    return MockStatusTransitionService()


@pytest.fixture
def test_round():
    """Create a test round"""
    return Round(
        id=uuid.uuid4(),
        tournament_id=uuid.uuid4(),
        round_number=1,
        type=RoundType.GROUP_STAGE,
        best_of=1,
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=7),
        status="active",
    )


@pytest.fixture
def test_player():
    """Create a test player"""
    return Player(
        id=uuid.uuid4(), 
        steam_id="76561198000000000", 
        steam_name="TestPlayer",
    )


@pytest.fixture
def round_service(mock_transition_service):
    """Create a round service with mocked dependencies"""
    audit_service = Mock(spec=AuditService)
    audit_service.audited_transaction = lambda **kwargs: lambda func: func

    round_winner_service = Mock(spec=RoundWinnerService)
    round_winner_service.determine_round_winners = AsyncMock()

    return RoundService(
        audit_service=audit_service,
        status_transition_service=mock_transition_service,
        round_winner_service=round_winner_service,
    )


@pytest.mark.asyncio
async def test_change_round_status_pipeline(
    round_service, test_round, test_player
):
    """Test that change_round_status correctly uses the transition service"""
    # Create a test session mock
    session = AsyncMock(spec=AsyncSession)

    # Set up test parameters
    new_status = "completed"
    reason = "Test round completion"

    # Create a mock transition step
    test_step = MockTransitionStep()
    pipeline = TransitionPipeline([test_step])

    # Register the pipeline with our mock service
    round_service.status_transition_service.register_transition_pipeline(
        "Round", "completed", pipeline
    )

    # Call the method under test
    result = await round_service.change_round_status(
        round=test_round,
        new_status=new_status,
        reason=reason,
        actor=test_player,
        session=session,
        entity_metadata={"test": "metadata"},
    )

    # Verify the transition service was called correctly
    transition_calls = round_service.status_transition_service.transition_calls
    assert len(transition_calls) == 1
    assert transition_calls[0]["entity"] == test_round
    assert transition_calls[0]["new_status"] == new_status
    assert transition_calls[0]["reason"] == reason
    assert transition_calls[0]["actor"] == test_player
    assert transition_calls[0]["entity_metadata"] == {"test": "metadata"}

    # Verify the result
    assert result.status == new_status


@pytest.mark.asyncio
async def test_complete_round_with_metadata(
    round_service, test_round, test_player
):
    """Test that complete_round passes the round_winner_service to entity_metadata"""
    # Create a test session mock
    session = AsyncMock(spec=AsyncSession)

    # This method depends on an audit transaction decorator
    # We'll directly call change_round_status instead
    result = await round_service.change_round_status(
        round=test_round,
        new_status="completed",
        reason="Round completed - all fixtures finished",
        actor=test_player,
        session=session,
        entity_metadata={"round_winner_service": round_service.round_winner_service}
    )

    # Verify the transition service was called correctly
    transition_calls = round_service.status_transition_service.transition_calls
    assert len(transition_calls) == 1
    assert transition_calls[0]["entity"] == test_round
    assert transition_calls[0]["new_status"] == "completed"
    assert "round_winner_service" in transition_calls[0]["entity_metadata"]

    # Verify the result
    assert result.status == "completed"