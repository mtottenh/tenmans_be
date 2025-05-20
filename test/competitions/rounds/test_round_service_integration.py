"""Integration tests for RoundService with pipeline"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Player
from competitions.models.rounds import Round, RoundType
from competitions.models.tournaments import Tournament, TournamentState
from competitions.rounds.round_winner_service import RoundWinnerService
from competitions.rounds.service import RoundService, create_round_service
from status.service import StatusTransitionService, create_enhanced_status_transition_service


@pytest_asyncio.fixture
async def test_setup(session, admin_user):
    """Set up test data"""
    # Create tournament
    tournament = Tournament(
        id=uuid.uuid4(),
        name="Test Tournament",
        season_id=uuid.uuid4(),
        type="regular",
        status=TournamentState.IN_PROGRESS,
        scheduled_start_date=datetime.now(timezone.utc),
        scheduled_end_date=datetime.now(timezone.utc) + timedelta(days=30)
    )
    session.add(tournament)

    # Create round
    round_obj = Round(
        id=uuid.uuid4(),
        tournament_id=tournament.id,
        round_number=1,
        type=RoundType.GROUP_STAGE,
        best_of=1,
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=7),
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    session.add(round_obj)

    # Create next round
    next_round = Round(
        id=uuid.uuid4(),
        tournament_id=tournament.id,
        round_number=2,
        type=RoundType.KNOCKOUT,
        best_of=3,
        status="pending",
        start_date=datetime.now(timezone.utc) + timedelta(days=8),
        end_date=datetime.now(timezone.utc) + timedelta(days=15),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(next_round)

    await session.commit()
    await session.refresh(round_obj)
    await session.refresh(next_round)

    # Create services with pipeline support
    status_service = create_enhanced_status_transition_service()
    round_service = RoundService(
        status_transition_service=status_service,
        round_winner_service=RoundWinnerService()
    )

    return {
        "tournament": tournament,
        "round": round_obj,
        "next_round": next_round,
        "round_service": round_service,
    }


@pytest.mark.asyncio
async def test_complete_round_with_pipeline(test_setup, admin_user, session):
    """Test round completion with pipeline integration"""
    data = test_setup
    round_obj = data["round"]
    next_round = data["next_round"]
    round_service = data["round_service"]

    # Complete the round - this should trigger pipeline execution
    result = await round_service.complete_round(
        round=round_obj,
        actor=admin_user,
        session=session,
        entity_metadata={"round_winner_service": round_service.round_winner_service}
    )

    # Verify the round was completed
    assert result.status == "completed"

    # Refresh next round to verify pipeline effect (activation)
    await session.refresh(next_round)
    assert next_round.status == "active", "Pipeline should activate next round"


@pytest.mark.asyncio
async def test_round_status_change(test_setup, admin_user, session):
    """Test that change_round_status method passes correct params to transition service"""
    data = test_setup
    round_obj = data["round"]
    round_service = data["round_service"]

    # Use a spy or mock to verify the parameters
    original_transition_status = round_service.status_transition_service.transition_status

    # Track calls to transition_status
    calls = []

    async def transition_spy(*args, **kwargs):
        calls.append(kwargs)
        return await original_transition_status(*args, **kwargs)

    # Replace with our spy
    round_service.status_transition_service.transition_status = transition_spy

    # Call with new interface
    await round_service.change_round_status(
        round=round_obj,
        new_status="completed",
        reason="Test reason",
        actor=admin_user,
        session=session,
        entity_metadata={"test": "metadata"}
    )

    # Verify call parameters
    assert len(calls) == 1
    assert calls[0]["entity"] == round_obj
    assert calls[0]["new_status"] == "completed"
    assert calls[0]["reason"] == "Test reason"
    assert calls[0]["actor"] == admin_user
    assert "entity_metadata" in calls[0]
    assert calls[0]["entity_metadata"]["test"] == "metadata"