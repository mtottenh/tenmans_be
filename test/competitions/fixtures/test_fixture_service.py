"""Test suite for FixtureService business logic"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.service import AuditService
from auth.models import Player
from competitions.fixtures.schemas import (
    FixtureCreate,
    FixtureForfeit,
    FixtureReschedule,
    FixtureUpdate,
    MatchPlayerCreate,
)
from competitions.fixtures.service import FixtureService, FixtureServiceError
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.rounds import Round, RoundType
from competitions.models.tournaments import Tournament, TournamentState
from competitions.rounds.service import RoundService
from matches.models import Result
from teams.models import Team


@pytest.fixture
def mock_audit_service():
    """Mock AuditService for testing"""
    mock = Mock(spec=AuditService)
    mock.audited_transaction = Mock(return_value=lambda func: func)  # Mock decorator
    return mock


@pytest.fixture
def mock_round_service():
    """Mock RoundService for testing"""
    mock = Mock(spec=RoundService)
    mock.get_round_fixtures = AsyncMock()
    mock.progress_round = AsyncMock()
    return mock


@pytest.fixture
def fixture_service(mock_audit_service, mock_round_service):
    """Create FixtureService with mocked dependencies"""
    return FixtureService(
        audit_service=mock_audit_service, round_service=mock_round_service
    )


@pytest.fixture
def test_teams():
    """Create test teams"""
    return [
        Team(id=str(uuid.uuid4()), name="Team Alpha", tag="ALPHA"),
        Team(id=str(uuid.uuid4()), name="Team Beta", tag="BETA"),
    ]


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
        status="active",
    )


@pytest.fixture
def test_fixture(test_round, test_teams):
    """Create a test fixture"""
    return Fixture(
        id=str(uuid.uuid4()),
        tournament_id=test_round.tournament_id,
        round_id=test_round.id,
        team_1=test_teams[0].id,
        team_2=test_teams[1].id,
        sequence_number=1,
        best_of=1,
        status=FixtureStatus.SCHEDULED,
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=7),
    )


@pytest.fixture
def test_players():
    """Create test players"""
    return [
        Player(
            id=str(uuid.uuid4()),
            steam_id=f"7656119800000000{i}",
            steam_name=f"Player{i}",
        )
        for i in range(10)
    ]


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.mark.asyncio
async def test_create_fixture(
    fixture_service, test_tournament, test_round, test_teams, mock_session
):
    """Test creating a new fixture"""
    # Setup
    fixture_data = FixtureCreate(
        tournament_id=test_tournament.id,
        round_id=test_round.id,
        team_1=test_teams[0].id,
        team_2=test_teams[1].id,
        sequence_number=1,
        match_format='bo1',
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=7),
        notes="Test fixture",
    )

    # Mock tournament and round queries
    mock_tournament_result = Mock()
    mock_tournament_result.first.return_value = test_tournament

    mock_round_result = Mock()
    mock_round_result.first.return_value = test_round

    mock_session.execute.side_effect = [mock_tournament_result, mock_round_result]

    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    fixture = await fixture_service.create_fixture(
        fixture_data=fixture_data, actor=test_teams[0], session=mock_session
    )

    # Assert
    assert fixture is not None
    assert fixture.team_1 == test_teams[0].id
    assert fixture.team_2 == test_teams[1].id
    assert fixture.status == FixtureStatus.SCHEDULED

    # Verify database operations
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_fixture_invalid_tournament(
    fixture_service, test_round, test_teams, mock_session
):
    """Test error when creating fixture with invalid tournament"""
    # Setup
    fixture_data = FixtureCreate(
        tournament_id="invalid-id",
        round_id=test_round.id,
        team_1=test_teams[0].id,
        team_2=test_teams[1].id,
        sequence_number=1,
        best_of=1,
    )

    # Mock query returning None
    mock_result = Mock()
    mock_result.first.return_value = None
    mock_session.execute.return_value = mock_result

    # Execute and assert
    with pytest.raises(FixtureServiceError, match="Tournament not found"):
        await fixture_service.create_fixture(
            fixture_data=fixture_data, actor=test_teams[0], session=mock_session
        )


@pytest.mark.asyncio
async def test_update_fixture(fixture_service, test_fixture, mock_session):
    """Test updating an existing fixture"""
    # Setup
    update_data = FixtureUpdate(
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=14),
        match_format="online",
        notes="Updated fixture",
    )

    # Mock query
    mock_result = Mock()
    mock_result.first.return_value = test_fixture
    mock_session.execute.return_value = mock_result

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    updated = await fixture_service.update_fixture(
        fixture_id=test_fixture.id,
        update_data=update_data,
        actor=Mock(),
        session=mock_session,
    )

    # Assert
    assert updated.notes == "Updated fixture"
    assert updated.match_format == "online"
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_reschedule_fixture(fixture_service, test_fixture, mock_session):
    """Test rescheduling a fixture"""
    # Setup
    new_time = datetime.now(timezone.utc) + timedelta(days=14)
    reschedule_data = FixtureReschedule(
        new_scheduled_at=new_time, reason="Team conflict"
    )

    # Mock query
    mock_result = Mock()
    mock_result.first.return_value = test_fixture
    mock_session.execute.return_value = mock_result

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    updated = await fixture_service.reschedule_fixture(
        fixture_id=test_fixture.id,
        reschedule_data=reschedule_data,
        actor=Mock(),
        session=mock_session,
    )

    # Assert
    assert updated.scheduled_at == new_time
    assert updated.status == FixtureStatus.SCHEDULED
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_reschedule_completed_fixture(
    fixture_service, test_fixture, mock_session
):
    """Test error when trying to reschedule completed fixture"""
    # Setup
    test_fixture.status = FixtureStatus.COMPLETED

    reschedule_data = FixtureReschedule(
        new_scheduled_at=datetime.now(timezone.utc) + timedelta(days=14),
        reason="Invalid reschedule",
    )

    # Mock query
    mock_result = Mock()
    mock_result.first.return_value = test_fixture
    mock_session.execute.return_value = mock_result

    # Execute and assert
    with pytest.raises(FixtureServiceError, match="Cannot reschedule"):
        await fixture_service.reschedule_fixture(
            fixture_id=test_fixture.id,
            reschedule_data=reschedule_data,
            actor=Mock(),
            session=mock_session,
        )


@pytest.mark.asyncio
async def test_start_fixture(fixture_service, test_fixture, mock_session):
    """Test starting a fixture"""
    # Setup
    # Mock query
    mock_result = Mock()
    mock_result.first.return_value = test_fixture
    mock_session.execute.return_value = mock_result

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    updated = await fixture_service.start_fixture(
        fixture_id=test_fixture.id, actor=Mock(), session=mock_session
    )

    # Assert
    assert updated.status == FixtureStatus.IN_PROGRESS
    assert updated.started_at is not None
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_forfeit_fixture(fixture_service, test_fixture, test_teams, mock_session):
    """Test forfeiting a fixture"""
    # Setup
    forfeit_data = FixtureForfeit(
        forfeit_team_id=test_teams[0].id, reason="Team didn't show up"
    )

    test_fixture.status = FixtureStatus.IN_PROGRESS

    # Mock fixture query
    mock_fixture_result = Mock()
    mock_fixture_result.first.return_value = test_fixture

    # Mock team query
    mock_team_result = Mock()
    mock_team_result.first.return_value = test_teams[0]

    mock_session.execute.side_effect = [mock_fixture_result, mock_team_result]

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    updated = await fixture_service.forfeit_fixture(
        fixture_id=test_fixture.id,
        forfeit_data=forfeit_data,
        actor=Mock(),
        session=mock_session,
    )

    # Assert
    assert updated.status == FixtureStatus.FORFEIT
    assert updated.forfeit_winner == test_teams[1].id  # Other team wins
    assert updated.forfeit_reason == "Team didn't show up"
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_complete_fixture(
    fixture_service, test_fixture, test_teams, mock_session
):
    """Test completing a fixture"""
    # Setup
    test_fixture.status = FixtureStatus.IN_PROGRESS

    # Create results
    results = [
        Result(
            id=str(uuid.uuid4()),
            fixture_id=test_fixture.id,
            map_number=1,
            team_1_score=16,
            team_2_score=14,
            confirmation_status="confirmed",
        )
    ]

    # Mock queries
    mock_fixture_result = Mock()
    mock_fixture_result.first.return_value = test_fixture

    mock_results_result = Mock()
    mock_results_result.all.return_value = results

    mock_scalars = Mock(return_value=mock_results_result)

    mock_session.execute.side_effect = [mock_fixture_result, Mock(scalars=mock_scalars)]

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    updated = await fixture_service.complete_fixture(
        fixture_id=test_fixture.id, actor=Mock(), session=mock_session
    )

    # Assert
    assert updated.status == FixtureStatus.COMPLETED
    assert updated.winner == test_teams[0].id  # Team 1 won
    assert updated.completed_at is not None
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_fixture_with_details(
    fixture_service, test_fixture, test_teams, mock_session
):
    """Test getting fixture with full details"""
    # Setup
    # Mock fixture query with relationships
    mock_result = Mock()
    test_fixture.team_1_ref = test_teams[0]
    test_fixture.team_2_ref = test_teams[1]
    mock_result.first.return_value = test_fixture
    mock_unique = Mock(return_value=mock_result)
    mock_session.execute.return_value.unique = mock_unique

    # Execute
    fixture = await fixture_service.get_fixture_with_details(
        fixture_id=test_fixture.id, session=mock_session
    )

    # Assert
    assert fixture is not None
    assert fixture.team_1_ref == test_teams[0]
    assert fixture.team_2_ref == test_teams[1]


@pytest.mark.asyncio
async def test_get_round_fixtures(
    fixture_service, test_round, test_fixture, mock_session
):
    """Test getting all fixtures for a round"""
    # Setup
    fixtures = [
        test_fixture,
        Fixture(
            id=str(uuid.uuid4()),
            tournament_id=test_round.tournament_id,
            round_id=test_round.id,
            team_1=str(uuid.uuid4()),
            team_2=str(uuid.uuid4()),
            sequence_number=2,
            best_of=1,
            status=FixtureStatus.SCHEDULED,
        ),
    ]

    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = fixtures
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars

    # Execute
    result = await fixture_service.get_round_fixtures(
        round_id=test_round.id, session=mock_session
    )

    # Assert
    assert len(result) == 2
    assert all(f.round_id == test_round.id for f in result)


@pytest.mark.asyncio
async def test_get_team_fixtures(
    fixture_service, test_tournament, test_teams, test_fixture, mock_session
):
    """Test getting all fixtures for a team in a tournament"""
    # Setup
    team_id = test_teams[0].id
    fixtures = [test_fixture]

    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = fixtures
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars

    # Execute
    result = await fixture_service.get_team_fixtures(
        team_id=team_id, tournament_id=test_tournament.id, session=mock_session
    )

    # Assert
    assert len(result) == 1
    assert team_id in {result[0].team_1, result[0].team_2}


@pytest.mark.asyncio
async def test_update_fixture_status(fixture_service, test_fixture, mock_session):
    """Test updating fixture status"""
    # Setup
    new_status = FixtureStatus.IN_PROGRESS

    # Mock query
    mock_result = Mock()
    mock_result.first.return_value = test_fixture
    mock_session.execute.return_value = mock_result

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Execute
    updated = await fixture_service.update_fixture_status(
        fixture_id=test_fixture.id,
        status=new_status,
        actor=Mock(),
        session=mock_session,
    )

    # Assert
    assert updated.status == new_status
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_assign_match_players(
    fixture_service, test_fixture, test_players, mock_session
):
    """Test assigning players to a match"""
    # Setup
    player_assignments = [
        MatchPlayerCreate(
            player_id=test_players[i].id,
            team_id=test_fixture.team_1 if i < 5 else test_fixture.team_2,
            roster_position=i % 5 + 1,
        )
        for i in range(10)
    ]

    # Mock fixture query
    mock_result = Mock()
    mock_result.first.return_value = test_fixture
    mock_session.execute.return_value = mock_result

    mock_session.add_all = Mock()
    mock_session.commit = AsyncMock()

    # Execute
    match_players = await fixture_service.assign_match_players(
        fixture_id=test_fixture.id,
        player_assignments=player_assignments,
        actor=Mock(),
        session=mock_session,
    )

    # Assert
    assert len(match_players) == 10
    assert all(mp.fixture_id == test_fixture.id for mp in match_players)
    mock_session.add_all.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_tournament_fixtures(
    fixture_service, test_tournament, test_fixture, mock_session
):
    """Test getting all fixtures for a tournament"""
    # Setup
    fixtures = [
        test_fixture,
        Fixture(
            id=str(uuid.uuid4()),
            tournament_id=test_tournament.id,
            round_id=str(uuid.uuid4()),
            team_1=str(uuid.uuid4()),
            team_2=str(uuid.uuid4()),
            sequence_number=2,
            best_of=3,
            status=FixtureStatus.SCHEDULED,
        ),
    ]

    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = fixtures
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars

    # Execute
    result = await fixture_service.get_tournament_fixtures(
        tournament_id=test_tournament.id, session=mock_session
    )

    # Assert
    assert len(result) == 2
    assert all(f.tournament_id == test_tournament.id for f in result)
