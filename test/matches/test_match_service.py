"""Test suite for MatchService business logic"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
import uuid

from matches.service import MatchService, MatchServiceError
from matches.models import Result, MatchPlayer, ConfirmationStatus
from matches.schemas import (
    ResultCreate,
    ResultConfirm,
    ResultDispute,
    AdminResultOverride,
    MatchPlayerAdd
)
from competitions.models.fixtures import Fixture, FixtureStatus
from teams.models import Team, TeamCaptain, Roster
from auth.models import Player
from maps.models import Map
from audit.service import AuditService
from competitions.fixtures.service import FixtureService


@pytest.fixture
def mock_audit_service():
    """Mock AuditService for testing"""
    mock = Mock(spec=AuditService)
    mock.audited_transaction = Mock(return_value=lambda func: func)  # Mock decorator
    return mock


@pytest.fixture
def mock_fixture_service():
    """Mock FixtureService for testing"""
    mock = Mock(spec=FixtureService)
    mock.get_fixture_with_details = AsyncMock()
    mock.complete_fixture = AsyncMock()
    return mock


@pytest.fixture
def match_service(mock_audit_service, mock_fixture_service):
    """Create MatchService with mocked dependencies"""
    return MatchService(
        audit_service=mock_audit_service,
        fixture_service=mock_fixture_service
    )


@pytest.fixture
def test_teams():
    """Create test teams"""
    return [
        Team(id=str(uuid.uuid4()), name="Team Alpha", tag="ALPHA"),
        Team(id=str(uuid.uuid4()), name="Team Beta", tag="BETA")
    ]


@pytest.fixture
def test_fixture(test_teams):
    """Create a test fixture"""
    return Fixture(
        id=str(uuid.uuid4()),
        tournament_id=str(uuid.uuid4()),
        round_id=str(uuid.uuid4()),
        team_1=test_teams[0].id,
        team_2=test_teams[1].id,
        sequence_number=1,
        best_of=1,
        status=FixtureStatus.IN_PROGRESS
    )


@pytest.fixture
def test_players():
    """Create test players"""
    return [
        Player(id=str(uuid.uuid4()), steam_id=f"7656119800000000{i}", steam_name=f"Player{i}")
        for i in range(10)
    ]


@pytest.fixture
def test_map():
    """Create a test map"""
    return Map(
        id=str(uuid.uuid4()),
        name="de_dust2",
        display_name="Dust II",
        active=True
    )


@pytest.fixture
def test_result(test_fixture, test_map, test_players):
    """Create a test result"""
    return Result(
        id=str(uuid.uuid4()),
        fixture_id=test_fixture.id,
        map_id=test_map.id,
        map_number=1,
        team_1_score=16,
        team_2_score=14,
        team_1_side_first="CT",
        confirmation_status=ConfirmationStatus.PENDING,
        submitted_by=test_players[0].id,
        created_at=datetime.now()
    )


@pytest.fixture
def test_team_captain(test_teams, test_players):
    """Create a test team captain"""
    return TeamCaptain(
        id=str(uuid.uuid4()),
        team_id=test_teams[0].id,
        player_id=test_players[0].id,
        assigned_at=datetime.now()
    )


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.mark.asyncio
async def test_submit_result(
    match_service,
    test_fixture,
    test_teams,
    test_players,
    test_map,
    test_team_captain,
    mock_fixture_service,
    mock_session
):
    """Test submitting a match result"""
    # Setup
    result_data = ResultCreate(
        fixture_id=test_fixture.id,
        map_id=test_map.id,
        map_number=1,
        team_1_score=16,
        team_2_score=14,
        team_1_side_first="CT",
        match_duration=timedelta(minutes=45),
        notes="GG WP"
    )
    
    # Mock fixture service
    mock_fixture_service.get_fixture_with_details.return_value = test_fixture
    
    # Mock captain check
    mock_captain_result = Mock()
    mock_captain_result.first.return_value = test_team_captain
    mock_session.execute.return_value = mock_captain_result
    
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    result = await match_service.submit_result(
        result_data=result_data,
        submitted_by=test_players[0],
        session=mock_session
    )
    
    # Assert
    assert result is not None
    assert result.fixture_id == test_fixture.id
    assert result.team_1_score == 16
    assert result.team_2_score == 14
    assert result.confirmation_status == ConfirmationStatus.PENDING
    
    # Verify database operations
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_submit_result_not_captain(
    match_service,
    test_fixture,
    test_players,
    test_map,
    mock_fixture_service,
    mock_session
):
    """Test error when non-captain tries to submit result"""
    # Setup
    result_data = ResultCreate(
        fixture_id=test_fixture.id,
        map_id=test_map.id,
        map_number=1,
        team_1_score=16,
        team_2_score=14,
        team_1_side_first="CT"
    )
    
    # Mock fixture service
    mock_fixture_service.get_fixture_with_details.return_value = test_fixture
    
    # Mock captain check - no captain found
    mock_captain_result = Mock()
    mock_captain_result.first.return_value = None
    mock_session.execute.return_value = mock_captain_result
    
    # Execute and assert
    with pytest.raises(MatchServiceError, match="not a captain"):
        await match_service.submit_result(
            result_data=result_data,
            submitted_by=test_players[5],  # Not a captain
            session=mock_session
        )


@pytest.mark.asyncio
async def test_confirm_result(
    match_service,
    test_result,
    test_fixture,
    test_teams,
    test_players,
    test_team_captain,
    mock_session
):
    """Test confirming a match result"""
    # Setup
    confirm_data = ResultConfirm(
        result_id=test_result.id,
        confirmed=True,
        notes="Confirmed"
    )
    
    # Make the second player captain of team 2
    team2_captain = TeamCaptain(
        id=str(uuid.uuid4()),
        team_id=test_teams[1].id,
        player_id=test_players[1].id
    )
    
    # Mock result query
    mock_result_query = Mock()
    mock_result_query.first.return_value = test_result
    
    # Mock fixture query
    test_fixture.team_1_ref = test_teams[0]
    test_fixture.team_2_ref = test_teams[1]
    mock_fixture_query = Mock()
    mock_fixture_query.first.return_value = test_fixture
    
    # Mock captain query
    mock_captain_query = Mock()
    mock_captain_query.first.return_value = team2_captain
    
    mock_session.execute.side_effect = [
        mock_result_query,
        mock_fixture_query,
        mock_captain_query
    ]
    
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    result = await match_service.confirm_result(
        confirm_data=confirm_data,
        confirmed_by=test_players[1],
        session=mock_session
    )
    
    # Assert
    assert result.confirmation_status == ConfirmationStatus.CONFIRMED
    assert result.confirmed_by == test_players[1].id
    assert result.confirmed_at is not None
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_result_already_confirmed(
    match_service,
    test_result,
    test_players,
    mock_session
):
    """Test error when trying to confirm already confirmed result"""
    # Setup
    test_result.confirmation_status = ConfirmationStatus.CONFIRMED
    test_result.confirmed_by = test_players[1].id
    
    confirm_data = ResultConfirm(
        result_id=test_result.id,
        confirmed=True
    )
    
    # Mock query
    mock_result = Mock()
    mock_result.first.return_value = test_result
    mock_session.execute.return_value = mock_result
    
    # Execute and assert
    with pytest.raises(MatchServiceError, match="already confirmed"):
        await match_service.confirm_result(
            confirm_data=confirm_data,
            confirmed_by=test_players[1],
            session=mock_session
        )


@pytest.mark.asyncio
async def test_dispute_result(
    match_service,
    test_result,
    test_players,
    mock_session
):
    """Test disputing a match result"""
    # Setup
    test_result.confirmation_status = ConfirmationStatus.PENDING
    
    dispute_data = ResultDispute(
        result_id=test_result.id,
        reason="Incorrect score",
        evidence_urls=["https://example.com/screenshot.png"]
    )
    
    # Mock result query
    mock_result_query = Mock()
    mock_result_query.first.return_value = test_result
    mock_session.execute.return_value = mock_result_query
    
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    result = await match_service.dispute_result(
        dispute_data=dispute_data,
        disputed_by=test_players[1],
        session=mock_session
    )
    
    # Assert
    assert result.confirmation_status == ConfirmationStatus.DISPUTED
    assert result.dispute_reason == "Incorrect score"
    assert result.disputed_by == test_players[1].id
    assert result.disputed_at is not None
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_admin_override_result(
    match_service,
    test_result,
    test_fixture,
    test_players,
    mock_fixture_service,
    mock_session
):
    """Test admin override of match result"""
    # Setup
    override_data = AdminResultOverride(
        result_id=test_result.id,
        team_1_score=16,
        team_2_score=12,
        override_reason="Score correction after review",
        confirmed=True
    )
    
    # Mock result query
    mock_result_query = Mock()
    mock_result_query.first.return_value = test_result
    
    # Mock fixture query
    mock_fixture_query = Mock()
    mock_fixture_query.first.return_value = test_fixture
    
    mock_session.execute.side_effect = [mock_result_query, mock_fixture_query]
    
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    result = await match_service.admin_override_result(
        override_data=override_data,
        admin=test_players[9],  # Admin user
        session=mock_session
    )
    
    # Assert
    assert result.team_1_score == 16
    assert result.team_2_score == 12
    assert result.confirmation_status == ConfirmationStatus.CONFIRMED
    assert result.admin_override is True
    assert result.admin_override_by == test_players[9].id
    assert result.admin_override_reason == "Score correction after review"
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_add_match_player(
    match_service,
    test_fixture,
    test_players,
    test_teams,
    mock_session
):
    """Test adding a player to a match"""
    # Setup
    player_data = MatchPlayerAdd(
        fixture_id=test_fixture.id,
        player_id=test_players[0].id,
        team_id=test_teams[0].id,
        roster_position=1,
        stats={
            "kills": 25,
            "deaths": 18,
            "assists": 7
        }
    )
    
    # Mock existing check
    mock_existing_result = Mock()
    mock_existing_result.first.return_value = None
    
    # Mock roster check
    roster = Roster(
        id=str(uuid.uuid4()),
        team_id=test_teams[0].id,
        player_id=test_players[0].id,
        status="main"
    )
    mock_roster_result = Mock()
    mock_roster_result.first.return_value = roster
    
    mock_session.execute.side_effect = [mock_existing_result, mock_roster_result]
    
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    match_player = await match_service.add_match_player(
        player_data=player_data,
        actor=test_players[9],
        session=mock_session
    )
    
    # Assert
    assert match_player is not None
    assert match_player.fixture_id == test_fixture.id
    assert match_player.player_id == test_players[0].id
    assert match_player.team_id == test_teams[0].id
    assert match_player.stats["kills"] == 25
    
    # Verify database operations
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_fixture_results(
    match_service,
    test_fixture,
    test_result,
    mock_session
):
    """Test getting all results for a fixture"""
    # Setup
    results = [test_result, Result(
        id=str(uuid.uuid4()),
        fixture_id=test_fixture.id,
        map_id=str(uuid.uuid4()),
        map_number=2,
        team_1_score=14,
        team_2_score=16,
        team_1_side_first="T",
        confirmation_status=ConfirmationStatus.PENDING
    )]
    
    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = results
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    fixture_results = await match_service.get_fixture_results(
        fixture_id=test_fixture.id,
        session=mock_session
    )
    
    # Assert
    assert len(fixture_results) == 2
    assert all(r.fixture_id == test_fixture.id for r in fixture_results)
    assert fixture_results[0].map_number < fixture_results[1].map_number


@pytest.mark.asyncio
async def test_get_match_players(
    match_service,
    test_fixture,
    test_players,
    test_teams,
    mock_session
):
    """Test getting all players in a match"""
    # Setup
    match_players = [
        MatchPlayer(
            id=str(uuid.uuid4()),
            fixture_id=test_fixture.id,
            player_id=test_players[i].id,
            team_id=test_teams[0].id if i < 5 else test_teams[1].id,
            roster_position=i % 5 + 1
        )
        for i in range(10)
    ]
    
    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = match_players
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    players = await match_service.get_match_players(
        fixture_id=test_fixture.id,
        session=mock_session
    )
    
    # Assert
    assert len(players) == 10
    assert all(p.fixture_id == test_fixture.id for p in players)
    assert len([p for p in players if p.team_id == test_teams[0].id]) == 5
    assert len([p for p in players if p.team_id == test_teams[1].id]) == 5


@pytest.mark.asyncio
async def test_calculate_fixture_winner(
    match_service,
    test_fixture,
    test_teams,
    mock_session
):
    """Test calculating fixture winner from results"""
    # Setup
    results = [
        Result(
            id=str(uuid.uuid4()),
            fixture_id=test_fixture.id,
            map_id=str(uuid.uuid4()),
            map_number=1,
            team_1_score=16,
            team_2_score=14,
            confirmation_status=ConfirmationStatus.CONFIRMED
        ),
        Result(
            id=str(uuid.uuid4()),
            fixture_id=test_fixture.id,
            map_id=str(uuid.uuid4()),
            map_number=2,
            team_1_score=14,
            team_2_score=16,
            confirmation_status=ConfirmationStatus.CONFIRMED
        ),
        Result(
            id=str(uuid.uuid4()),
            fixture_id=test_fixture.id,
            map_id=str(uuid.uuid4()),
            map_number=3,
            team_1_score=16,
            team_2_score=10,
            confirmation_status=ConfirmationStatus.CONFIRMED
        )
    ]
    
    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = results
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    winner = await match_service.calculate_fixture_winner(
        fixture_id=test_fixture.id,
        session=mock_session
    )
    
    # Assert
    assert winner == test_teams[0].id  # Team 1 won 2-1


@pytest.mark.asyncio
async def test_validate_result_scores(
    match_service,
    test_result
):
    """Test validation of result scores"""
    # Test valid scores
    assert match_service.validate_result_scores(16, 14) is True
    assert match_service.validate_result_scores(16, 11) is True
    assert match_service.validate_result_scores(19, 17) is True  # Overtime
    
    # Test invalid scores
    assert match_service.validate_result_scores(16, 16) is False  # Tie
    assert match_service.validate_result_scores(15, 14) is False  # Neither team reached 16
    assert match_service.validate_result_scores(17, 14) is False  # Invalid overtime score
    assert match_service.validate_result_scores(-1, 16) is False  # Negative score


@pytest.mark.asyncio
async def test_get_player_match_history(
    match_service,
    test_players,
    test_fixture,
    mock_session
):
    """Test getting match history for a player"""
    # Setup
    player_id = test_players[0].id
    match_players = [
        MatchPlayer(
            id=str(uuid.uuid4()),
            fixture_id=test_fixture.id,
            player_id=player_id,
            team_id=str(uuid.uuid4()),
            roster_position=1,
            stats={"kills": 20, "deaths": 15}
        )
    ]
    
    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = match_players
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    history = await match_service.get_player_match_history(
        player_id=player_id,
        limit=10,
        session=mock_session
    )
    
    # Assert
    assert len(history) == 1
    assert history[0].player_id == player_id
    assert history[0].stats["kills"] == 20