"""Tests for the Round status transition pipeline"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from competitions.models.rounds import Round, RoundType
from competitions.models.tournaments import Tournament, TournamentState
from competitions.rounds.round_winner_service import RoundWinnerService
from status.pipeline import TransitionPipeline, TransitionStep
from status.service import StatusTransitionService, create_enhanced_status_transition_service
from status.transition_steps.round import RoundCompleteStep


class TestRoundCompleteTransitionStep(TransitionStep):
    """Test pipeline step for round completion, tracks execution"""

    def __init__(self):
        self.was_executed = False
        self.execution_context = {}

    async def execute(
        self,
        entity: Round,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Track execution and store context for verification"""
        self.was_executed = True
        self.execution_context = {
            "entity_id": entity.id,
            "old_status": old_status,
            "new_status": new_status,
            "actor_id": actor.id,
            "entity_metadata": context.get("entity_metadata", {})
        }

        # Call the real implementation if needed
        if context.get("call_real_implementation", False):
            real_step = RoundCompleteStep()
            await real_step.execute(
                entity=entity,
                old_status=old_status,
                new_status=new_status,
                actor=actor,
                session=session,
                audit_context=audit_context,
                **context
            )


@pytest.fixture
def test_round_pipeline():
    """Create a test round transition pipeline"""
    test_step = TestRoundCompleteTransitionStep()
    pipeline = TransitionPipeline([test_step])
    return pipeline, test_step


@pytest_asyncio.fixture
async def round_with_service(session: AsyncSession, admin_user: Player):
    """Create a test round with configured status transition service"""
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
    await session.commit()

    # Create and configure status transition service
    service = create_enhanced_status_transition_service()

    # Return all needed objects
    return round_obj, tournament, service


@pytest.mark.asyncio
async def test_round_pipeline_execution(
    round_with_service,
    test_round_pipeline,
    session: AsyncSession,
    admin_user: Player
):
    """Test that round status transition executes the pipeline"""
    round_obj, tournament, service = round_with_service
    pipeline, test_step = test_round_pipeline

    # Register our test pipeline instead of the real one
    service.register_transition_pipeline("Round", "completed", pipeline)

    # Create round winner service for entity metadata
    round_winner_service = RoundWinnerService()

    # Perform status transition with our test service
    updated_round = await service.transition_status(
        entity=round_obj,
        new_status="completed",
        reason="Test round completion",
        actor=admin_user,
        entity_metadata={"round_winner_service": round_winner_service},
        session=session
    )

    # Verify the pipeline step was executed
    assert test_step.was_executed is True
    assert test_step.execution_context["entity_id"] == round_obj.id
    assert test_step.execution_context["old_status"] == "active"
    assert test_step.execution_context["new_status"] == "completed"
    assert test_step.execution_context["actor_id"] == admin_user.id
    assert "round_winner_service" in test_step.execution_context["entity_metadata"]

    # Verify the entity status was updated
    assert updated_round.status == "completed"