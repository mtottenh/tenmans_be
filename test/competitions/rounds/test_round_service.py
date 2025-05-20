"""Test suite for RoundService business logic"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.service import AuditService
from auth.models import Player
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.rounds import Round, RoundType
from competitions.models.tournaments import Tournament, TournamentState
from competitions.rounds.round_winner_service import RoundWinnerService
from competitions.rounds.service import RoundService, RoundServiceError
from status.service import (
    StatusTransitionService,
)


@pytest.fixture
def mock_audit_service():
    """Mock AuditService for testing"""
    mock = Mock(spec=AuditService)
    mock.audited_transaction = Mock(return_value=lambda func: func)  # Mock decorator
    return mock


@pytest.fixture
def mock_status_transition_service():
    """Mock StatusTransitionService for testing"""
    mock = Mock(spec=StatusTransitionService)
    mock.transition_status = AsyncMock()
    mock.create_transition = AsyncMock()
    mock.register_transition_manager = Mock()
    return mock


@pytest.fixture
def mock_round_winner_service():
    """Mock RoundWinnerService for testing"""
    mock = Mock(spec=RoundWinnerService)
    mock.get_round_winner = AsyncMock()
    mock.determine_round_winners = AsyncMock()
    return mock


@pytest.fixture
def round_service(
    mock_audit_service, mock_status_transition_service, mock_round_winner_service
):
    """Create RoundService with mocked dependencies"""
    return RoundService(
        audit_service=mock_audit_service,
        status_transition_service=mock_status_transition_service,
        round_winner_service=mock_round_winner_service,
    )


@pytest.fixture
def test_tournament():
    """Create a test tournament"""
    return Tournament(
        id=str(uuid.uuid4()),
        season_id=str(uuid.uuid4()),
        tournament_type="regular",
        name="Test Tournament",
        state=TournamentState.IN_PROGRESS,
    )


@pytest.fixture
def test_round(test_tournament):
    """Create a test round"""
    return Round(
        id=str(uuid.uuid4()),
        tournament_id=test_tournament.id,
        round_number=1,
        type=RoundType.GROUP_STAGE,
        best_of=1,
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=7),
        status="active",
    )


@pytest.fixture
def test_teams():
    """Create test teams"""
    return [{"id": str(uuid.uuid4()), "name": f"Team {i}"} for i in range(4)]


@pytest.fixture
def test_fixtures(test_round, test_teams):
    """Create test fixtures for a round"""
    return [
        Fixture(
            id=str(uuid.uuid4()),
            tournament_id=test_round.tournament_id,
            round_id=test_round.id,
            team_1=test_teams[0]["id"],
            team_2=test_teams[1]["id"],
            sequence_number=1,
            best_of=1,
            status=FixtureStatus.SCHEDULED,
        ),
        Fixture(
            id=str(uuid.uuid4()),
            tournament_id=test_round.tournament_id,
            round_id=test_round.id,
            team_1=test_teams[2]["id"],
            team_2=test_teams[3]["id"],
            sequence_number=2,
            best_of=1,
            status=FixtureStatus.SCHEDULED,
        ),
    ]


@pytest.fixture
def test_player():
    """Create a test player"""
    return Player(
        id=str(uuid.uuid4()), steam_id="76561198000000000", steam_name="TestPlayer"
    )


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.mark.asyncio
async def test_change_round_status(
    round_service, test_round, test_player, mock_status_transition_service, mock_session
):
    """Test changing round status with transition service"""
    # Setup
    new_status = "completed"
    reason = "All fixtures completed"

    # Mock the transition service
    mock_status_transition_service.transition_status.return_value = test_round

    # Execute
    result = await round_service.change_round_status(
        round=test_round,
        new_status=new_status,
        reason=reason,
        actor=test_player,
        session=mock_session
    )

    # Assert
    assert result == test_round
    mock_status_transition_service.transition_status.assert_called_once_with(
        entity=test_round,
        new_status=new_status,
        reason=reason,
        actor=test_player,
        session=mock_session,
        entity_metadata=None,
        audit_context=None
    )


@pytest.mark.asyncio
async def test_create_round(round_service, test_tournament, test_player, mock_session):
    """Test creating a new round"""
    # Setup
    round_data = {
        "tournament_id": test_tournament.id,
        "round_number": 1,
        "type": RoundType.GROUP_STAGE,
        "best_of": 1,
        "start_date": datetime.now(timezone.utc),
        "end_date": datetime.now(timezone.utc) + timedelta(days=7),
    }

    # Mock tournament query
    mock_result = Mock()
    mock_result.first.return_value = test_tournament
    mock_session.execute.return_value = mock_result

    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    round_obj = await round_service.create_round(
        tournament_id=round_data["tournament_id"],
        round_type=round_data["type"],
        round_number=round_data["round_number"],
        best_of=round_data["best_of"],
        start_date=round_data["start_date"],
        end_date=round_data["end_date"],
        actor=test_player,
        session=mock_session
    )

    # Assert
    assert round_obj is not None
    assert round_obj.tournament_id == test_tournament.id
    assert round_obj.round_number == 1
    assert round_obj.type == RoundType.GROUP
    assert round_obj.status == "pending"

    # Verify database operations
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_round_invalid_tournament(
    round_service, test_player, mock_session
):
    """Test error when creating round with invalid tournament"""
    # Setup
    round_data = {
        "tournament_id": "invalid-id",
        "round_number": 1,
        "type": RoundType.GROUP_STAGE,
        "best_of": 1,
    }

    # Mock query returning None
    mock_result = Mock()
    mock_result.first.return_value = None
    mock_session.execute.return_value = mock_result

    # Execute and assert
    with pytest.raises(RoundServiceError, match="Tournament not found"):
        await round_service.create_round(
            tournament_id=round_data["tournament_id"],
            round_type=round_data["type"],
            round_number=round_data["round_number"],
            best_of=round_data["best_of"],
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=7),
            actor=test_player,
            session=mock_session
        )


@pytest.mark.asyncio
async def test_start_round(
    round_service, test_round, test_player, mock_status_transition_service, mock_session
):
    """Test starting a round"""
    # Setup
    test_round.status = "pending"

    # Mock status transition
    test_round_started = Round(**test_round.model_dump())
    test_round_started.status = "active"
    test_round_started.started_at = datetime.now(timezone.utc)
    mock_status_transition_service.transition_status.return_value = test_round_started

    # Execute
    result = await round_service.start_round(
        round=test_round, actor=test_player, session=mock_session
    )

    # Assert
    assert result.status == "active"
    mock_status_transition_service.transition_status.assert_called_once()


@pytest.mark.asyncio
async def test_complete_round(
    round_service, test_round, test_player, mock_status_transition_service, mock_session
):
    """Test completing a round"""
    # Setup
    test_round.status = "active"
    tournament_service = Mock()

    # Mock status transition
    test_round_completed = Round(**test_round.model_dump())
    test_round_completed.status = "completed"
    test_round_completed.completed_at = datetime.now(timezone.utc)
    mock_status_transition_service.transition_status.return_value = test_round_completed

    # Execute
    result = await round_service.complete_round(
        round=test_round,
        actor=test_player,
        session=mock_session,
        entity_metadata={"round_winner_service": mock_round_winner_service},
    )

    # Assert
    assert result.status == "completed"
    mock_status_transition_service.transition_status.assert_called_once()


@pytest.mark.asyncio
async def test_get_round_fixtures(
    round_service, test_round, test_fixtures, mock_session
):
    """Test getting all fixtures for a round"""
    # Setup
    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = test_fixtures
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars

    # Execute
    fixtures = await round_service.get_round_fixtures(
        round_id=test_round.id, session=mock_session
    )

    # Assert
    assert len(fixtures) == 2
    assert all(f.round_id == test_round.id for f in fixtures)


@pytest.mark.asyncio
async def test_check_round_completion(
    round_service, test_round, test_fixtures, mock_session
):
    """Test checking if all fixtures in a round are completed"""
    # Setup
    # Set all fixtures as completed
    for fixture in test_fixtures:
        fixture.status = FixtureStatus.COMPLETED

    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = test_fixtures
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars

    # Execute
    is_complete = await round_service.check_round_completion(
        round_id=test_round.id, session=mock_session
    )

    # Assert
    assert is_complete is True


@pytest.mark.asyncio
async def test_check_round_completion_incomplete(
    round_service, test_round, test_fixtures, mock_session
):
    """Test checking round completion with incomplete fixtures"""
    # Setup
    # Set one fixture as incomplete
    test_fixtures[0].status = FixtureStatus.COMPLETED
    test_fixtures[1].status = FixtureStatus.IN_PROGRESS

    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = test_fixtures
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars

    # Execute
    is_complete = await round_service.check_round_completion(
        round_id=test_round.id, session=mock_session
    )

    # Assert
    assert is_complete is False


@pytest.mark.asyncio
async def test_determine_round_winners(
    round_service, test_round, test_teams, mock_round_winner_service, mock_session
):
    """Test determining winners of a round"""
    # Setup
    winners = [test_teams[0]["id"], test_teams[2]["id"]]
    mock_round_winner_service.determine_round_winners.return_value = winners

    # Execute
    result = await round_service.determine_round_winners(
        round=test_round, session=mock_session
    )

    # Assert
    assert result == winners
    assert len(result) == 2
    mock_round_winner_service.determine_round_winners.assert_called_once_with(
        round=test_round, session=mock_session
    )


@pytest.mark.asyncio
async def test_get_round_standings(
    round_service, test_round, test_teams, test_fixtures, mock_session
):
    """Test getting standings for a round"""
    # Setup
    # Mock fixture query
    mock_fixture_result = Mock()
    mock_fixture_result.all.return_value = test_fixtures

    # Create standings data
    standings = [
        {"team_id": team["id"], "points": 3, "wins": 1, "losses": 0}
        for team in test_teams[:2]
    ]

    # Mock standings calculation
    with patch.object(
        round_service, "calculate_round_standings", return_value=standings
    ):
        # Execute
        result = await round_service.get_round_standings(
            round=test_round, session=mock_session
        )

    # Assert
    assert len(result) == 2
    assert all("team_id" in s for s in result)
    assert all("points" in s for s in result)


@pytest.mark.asyncio
async def test_get_tournament_rounds(
    round_service, test_tournament, test_round, mock_session
):
    """Test getting all rounds for a tournament"""
    # Setup
    rounds = [
        test_round,
        Round(
            id=str(uuid.uuid4()),
            tournament_id=test_tournament.id,
            round_number=2,
            type=RoundType.KNOCKOUT,
            best_of=3,
            status="pending",
        ),
    ]

    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = rounds
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars

    # Execute
    result = await round_service.get_tournament_rounds(
        tournament_id=test_tournament.id, session=mock_session
    )

    # Assert
    assert len(result) == 2
    assert all(r.tournament_id == test_tournament.id for r in result)
    assert result[0].round_number < result[1].round_number


@pytest.mark.asyncio
async def test_advance_teams_to_next_round(
    round_service, test_round, test_teams, test_player, mock_session
):
    """Test advancing teams to the next round"""
    # Setup
    winning_teams = [test_teams[0]["id"], test_teams[2]["id"]]
    next_round = Round(
        id=str(uuid.uuid4()),
        tournament_id=test_round.tournament_id,
        round_number=test_round.round_number + 1,
        type=RoundType.KNOCKOUT,
        best_of=3,
        status="pending",
    )

    # Mock next round query
    mock_result = Mock()
    mock_result.first.return_value = next_round
    mock_session.execute.return_value = mock_result

    mock_session.add_all = Mock()
    mock_session.commit = AsyncMock()

    # Execute
    await round_service.advance_teams_to_next_round(
        current_round=test_round,
        winning_teams=winning_teams,
        actor=test_player,
        session=mock_session,
    )

    # Assert
    mock_session.add_all.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_round_dates(round_service, test_round, test_player, mock_session):
    """Test updating round dates"""
    # Setup
    new_start = datetime.now(timezone.utc) + timedelta(days=14)
    new_end = new_start + timedelta(days=7)

    # Mock query
    mock_result = Mock()
    mock_result.first.return_value = test_round
    mock_session.execute.return_value = mock_result

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    updated = await round_service.update_round_dates(
        round_id=test_round.id,
        start_date=new_start,
        end_date=new_end,
        actor=test_player,
        session=mock_session,
    )

    # Assert
    assert updated.start_date == new_start
    assert updated.end_date == new_end
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_round(
    round_service, test_round, test_player, mock_status_transition_service, mock_session
):
    """Test canceling a round"""
    # Setup
    test_round.status = "active"
    reason = "Tournament canceled"

    # Mock status transition
    test_round_canceled = Round(**test_round.model_dump())
    test_round_canceled.status = "cancelled"
    mock_status_transition_service.transition_status.return_value = test_round_canceled

    # Execute
    result = await round_service.cancel_round(
        round=test_round, reason=reason, actor=test_player, session=mock_session
    )

    # Assert
    assert result.status == "cancelled"
    mock_status_transition_service.transition_status.assert_called_once()


@pytest.mark.asyncio
async def test_round_complete_with_transition(
    round_service,
    test_round,
    test_fixtures,
    test_player,
    mock_status_transition_service,
    mock_round_winner_service,
    mock_session,
):
    """Test completion of a round with transition service"""
    # Setup
    test_round.status = "active"

    # Mark all fixtures as completed
    for fixture in test_fixtures:
        fixture.status = FixtureStatus.COMPLETED

    # Mock queries
    mock_fixture_result = Mock()
    mock_fixture_result.all.return_value = test_fixtures
    mock_scalars = Mock(return_value=mock_fixture_result)
    mock_session.execute.return_value.scalars = mock_scalars

    # Mock winner determination
    winners = ["team1", "team2"]
    mock_round_winner_service.determine_round_winners.return_value = winners

    # Mock status transition
    test_round_completed = Round(**test_round.model_dump())
    test_round_completed.status = "completed"
    mock_status_transition_service.transition_status.return_value = test_round_completed

    # Execute
    result = await round_service.complete_round(
        round=test_round, 
        actor=test_player, 
        session=mock_session,
        entity_metadata={"round_winner_service": mock_round_winner_service}
    )

    # Assert
    assert result.status == "completed"
    mock_status_transition_service.transition_status.assert_called_once()
