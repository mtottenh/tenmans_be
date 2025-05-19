"""Test suite for AvailabilityService business logic"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, date
from unittest.mock import Mock, AsyncMock, patch
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
import uuid

from availability.service import AvailabilityService, AvailabilityServiceError
from auth.models import Player
from competitions.models.scheduling import (
    PlayerAvailability,
    TeamAvailability,
    ScheduleSuggestion,
    ScheduleConflict,
    AvailabilityType,
    AvailabilityStatus
)
from competitions.models.tournaments import Tournament, TournamentType
from teams.models import Team, Roster
from teams.base_schemas import RosterStatus
from audit.service import AuditService
from status.service import StatusTransitionService


@pytest.fixture
def mock_audit_service():
    """Mock AuditService for testing"""
    mock = Mock(spec=AuditService)
    mock.audit_operation = AsyncMock()
    return mock


@pytest.fixture
def mock_status_transition_service():
    """Mock StatusTransitionService for testing"""
    mock = Mock(spec=StatusTransitionService)
    mock.transition_status = AsyncMock()
    return mock


@pytest.fixture
def availability_service(mock_audit_service, mock_status_transition_service):
    """Create AvailabilityService with mocked dependencies"""
    return AvailabilityService(
        audit_service=mock_audit_service,
        status_transition_service=mock_status_transition_service
    )


@pytest.fixture
def test_player():
    """Create a test player"""
    return Player(
        id=str(uuid.uuid4()),
        steam_id="76561198000000000",
        steam_name="TestPlayer",
        email="test@example.com",
        status="active"
    )


@pytest.fixture
def test_team():
    """Create a test team"""
    return Team(
        id=str(uuid.uuid4()),
        name="Test Team",
        tag="TEST",
        status="active"
    )


@pytest.fixture
def test_tournament():
    """Create a test tournament"""
    return Tournament(
        id=str(uuid.uuid4()),
        season_id=str(uuid.uuid4()),
        tournament_type=TournamentType.REGULAR,
        name="Test Tournament",
        status="active"
    )


@pytest.fixture
def test_roster(test_team, test_player):
    """Create a test roster entry"""
    return Roster(
        id=str(uuid.uuid4()),
        team_id=test_team.id,
        player_id=test_player.id,
        status=RosterStatus.MAIN,
        elo=1500
    )


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.mark.asyncio
async def test_submit_player_availability(
    availability_service,
    test_player,
    test_tournament,
    mock_session
):
    """Test submitting player availability for a tournament"""
    # Setup
    start_time = datetime.now() + timedelta(days=7)
    end_time = start_time + timedelta(hours=4)
    
    availability_data = {
        "tournament_id": test_tournament.id,
        "start_time": start_time,
        "end_time": end_time,
        "availability_type": AvailabilityType.AVAILABLE,
        "notes": "Ready to play"
    }
    
    # Mock the check for existing availability
    mock_result = Mock()
    mock_result.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    availability = await availability_service.submit_player_availability(
        player=test_player,
        availability_data=availability_data,
        session=mock_session
    )
    
    # Assert
    assert availability is not None
    assert availability.player_id == test_player.id
    assert availability.tournament_id == test_tournament.id
    assert availability.availability_type == AvailabilityType.AVAILABLE
    
    # Verify database operations
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_submit_duplicate_availability(
    availability_service,
    test_player,
    test_tournament,
    mock_session
):
    """Test error when submitting duplicate availability"""
    # Setup
    existing_availability = PlayerAvailability(
        id=str(uuid.uuid4()),
        player_id=test_player.id,
        tournament_id=test_tournament.id,
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=2),
        availability_type=AvailabilityType.AVAILABLE
    )
    
    # Mock existing availability
    mock_result = Mock()
    mock_result.first.return_value = existing_availability
    mock_session.execute.return_value = mock_result
    
    availability_data = {
        "tournament_id": test_tournament.id,
        "start_time": datetime.now() + timedelta(days=1),
        "end_time": datetime.now() + timedelta(days=1, hours=2),
        "availability_type": AvailabilityType.AVAILABLE
    }
    
    # Execute and assert
    with pytest.raises(AvailabilityServiceError, match="already submitted availability"):
        await availability_service.submit_player_availability(
            player=test_player,
            availability_data=availability_data,
            session=mock_session
        )


@pytest.mark.asyncio
async def test_update_player_availability(
    availability_service,
    test_player,
    mock_session
):
    """Test updating existing player availability"""
    # Setup
    availability_id = str(uuid.uuid4())
    existing_availability = PlayerAvailability(
        id=availability_id,
        player_id=test_player.id,
        tournament_id=str(uuid.uuid4()),
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=2),
        availability_type=AvailabilityType.AVAILABLE,
        status=AvailabilityStatus.CONFIRMED
    )
    
    # Mock the query
    mock_result = Mock()
    mock_result.first.return_value = existing_availability
    mock_session.execute.return_value = mock_result
    
    update_data = {
        "availability_type": AvailabilityType.MAYBE,
        "notes": "Might be late"
    }
    
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    updated = await availability_service.update_player_availability(
        availability_id=availability_id,
        player=test_player,
        update_data=update_data,
        session=mock_session
    )
    
    # Assert
    assert updated.availability_type == AvailabilityType.MAYBE
    assert updated.notes == "Might be late"
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_availability_wrong_player(
    availability_service,
    test_player,
    mock_session
):
    """Test error when trying to update another player's availability"""
    # Setup
    availability_id = str(uuid.uuid4())
    other_player_id = str(uuid.uuid4())
    
    existing_availability = PlayerAvailability(
        id=availability_id,
        player_id=other_player_id,  # Different player
        tournament_id=str(uuid.uuid4()),
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=2),
        availability_type=AvailabilityType.AVAILABLE
    )
    
    # Mock the query
    mock_result = Mock()
    mock_result.first.return_value = existing_availability
    mock_session.execute.return_value = mock_result
    
    update_data = {"availability_type": AvailabilityType.MAYBE}
    
    # Execute and assert
    with pytest.raises(AvailabilityServiceError, match="not authorized"):
        await availability_service.update_player_availability(
            availability_id=availability_id,
            player=test_player,
            update_data=update_data,
            session=mock_session
        )


@pytest.mark.asyncio
async def test_delete_player_availability(
    availability_service,
    test_player,
    mock_session
):
    """Test deleting player availability"""
    # Setup
    availability_id = str(uuid.uuid4())
    existing_availability = PlayerAvailability(
        id=availability_id,
        player_id=test_player.id,
        tournament_id=str(uuid.uuid4()),
        start_time=datetime.now() + timedelta(days=7),
        end_time=datetime.now() + timedelta(days=7, hours=2),
        availability_type=AvailabilityType.AVAILABLE
    )
    
    # Mock the query
    mock_result = Mock()
    mock_result.first.return_value = existing_availability
    mock_session.execute.return_value = mock_result
    
    mock_session.delete = Mock()
    mock_session.commit = AsyncMock()
    
    # Execute
    await availability_service.delete_player_availability(
        availability_id=availability_id,
        player=test_player,
        session=mock_session
    )
    
    # Assert
    mock_session.delete.assert_called_once_with(existing_availability)
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_player_availability_for_tournament(
    availability_service,
    test_player,
    test_tournament,
    mock_session
):
    """Test retrieving player's availability for a tournament"""
    # Setup
    availabilities = [
        PlayerAvailability(
            id=str(uuid.uuid4()),
            player_id=test_player.id,
            tournament_id=test_tournament.id,
            start_time=datetime.now() + timedelta(days=i),
            end_time=datetime.now() + timedelta(days=i, hours=4),
            availability_type=AvailabilityType.AVAILABLE
        )
        for i in range(3)
    ]
    
    # Mock the query
    mock_result = Mock()
    mock_result.all.return_value = availabilities
    mock_scalars = Mock()
    mock_scalars.return_value = mock_result
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    result = await availability_service.get_player_availability_for_tournament(
        player_id=test_player.id,
        tournament_id=test_tournament.id,
        session=mock_session
    )
    
    # Assert
    assert len(result) == 3
    assert all(a.player_id == test_player.id for a in result)
    assert all(a.tournament_id == test_tournament.id for a in result)


@pytest.mark.asyncio
async def test_calculate_team_availability(
    availability_service,
    test_team,
    test_tournament,
    test_roster,
    mock_session
):
    """Test calculating team availability based on player availabilities"""
    # Setup
    players = [
        Player(id=str(uuid.uuid4()), steam_id=f"7656119800000000{i}", steam_name=f"Player{i}")
        for i in range(5)
    ]
    
    rosters = [
        Roster(
            id=str(uuid.uuid4()),
            team_id=test_team.id,
            player_id=player.id,
            status=RosterStatus.MAIN
        )
        for player in players
    ]
    
    # Mock roster query
    mock_roster_result = Mock()
    mock_roster_result.all.return_value = rosters
    
    # Mock availability query - all players available at same time
    start_time = datetime.now() + timedelta(days=7)
    end_time = start_time + timedelta(hours=4)
    
    availabilities = [
        PlayerAvailability(
            id=str(uuid.uuid4()),
            player_id=player.id,
            tournament_id=test_tournament.id,
            start_time=start_time,
            end_time=end_time,
            availability_type=AvailabilityType.AVAILABLE
        )
        for player in players
    ]
    
    # Set up multiple mock returns
    mock_availability_results = [Mock() for _ in players]
    for i, mock_result in enumerate(mock_availability_results):
        mock_result.all.return_value = [availabilities[i]]
    
    # Configure mock session to return different results
    mock_scalars = Mock()
    mock_scalars.side_effect = [
        Mock(all=Mock(return_value=rosters)),  # First call for rosters
        *[Mock(all=Mock(return_value=[avail])) for avail in availabilities]  # Subsequent calls for availabilities
    ]
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    team_availabilities = await availability_service.calculate_team_availability(
        team=test_team,
        tournament=test_tournament,
        session=mock_session
    )
    
    # Assert
    assert len(team_availabilities) > 0
    first_availability = team_availabilities[0]
    assert first_availability.team_id == test_team.id
    assert first_availability.tournament_id == test_tournament.id
    assert first_availability.available_player_count == 5  # All players available


@pytest.mark.asyncio
async def test_find_conflicts_for_schedule(
    availability_service,
    test_tournament,
    test_team,
    mock_session
):
    """Test finding scheduling conflicts"""
    # Setup
    proposed_time = datetime.now() + timedelta(days=7)
    
    # Create teams with partial availability
    teams = [test_team, Team(id=str(uuid.uuid4()), name="Team B", tag="TB")]
    
    # Mock availability check - Team A has full availability, Team B has partial
    team_availabilities = [
        TeamAvailability(
            id=str(uuid.uuid4()),
            team_id=teams[0].id,
            tournament_id=test_tournament.id,
            start_time=proposed_time,
            end_time=proposed_time + timedelta(hours=2),
            available_player_count=5,
            total_player_count=5
        ),
        TeamAvailability(
            id=str(uuid.uuid4()),
            team_id=teams[1].id,
            tournament_id=test_tournament.id,
            start_time=proposed_time,
            end_time=proposed_time + timedelta(hours=2),
            available_player_count=3,  # Only 3 of 5 available
            total_player_count=5
        )
    ]
    
    # Mock the query results
    mock_result = Mock()
    mock_result.all.return_value = team_availabilities
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    conflicts = await availability_service.find_conflicts_for_schedule(
        tournament=test_tournament,
        teams=teams,
        proposed_time=proposed_time,
        duration_hours=2,
        session=mock_session
    )
    
    # Assert
    assert len(conflicts) == 1  # One team has conflict
    conflict = conflicts[0]
    assert conflict.team_id == teams[1].id
    assert conflict.conflict_type == "INSUFFICIENT_PLAYERS"
    assert "3 of 5" in conflict.description


@pytest.mark.asyncio
async def test_suggest_optimal_schedules(
    availability_service,
    test_tournament,
    test_team,
    mock_session
):
    """Test suggesting optimal schedules based on availability"""
    # Setup
    teams = [test_team, Team(id=str(uuid.uuid4()), name="Team B", tag="TB")]
    
    # Create availability windows
    availabilities = []
    for day_offset in range(7):
        start_time = datetime.now() + timedelta(days=day_offset, hours=18)
        availabilities.append(
            TeamAvailability(
                id=str(uuid.uuid4()),
                team_id=test_team.id,
                tournament_id=test_tournament.id,
                start_time=start_time,
                end_time=start_time + timedelta(hours=6),
                available_player_count=5,
                total_player_count=5
            )
        )
    
    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = availabilities
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    
    # Execute
    suggestions = await availability_service.suggest_optimal_schedules(
        tournament=test_tournament,
        teams=teams,
        min_duration_hours=2,
        max_suggestions=3,
        session=mock_session
    )
    
    # Assert
    assert len(suggestions) <= 3
    assert all(s.tournament_id == test_tournament.id for s in suggestions)
    assert all(s.confidence_score > 0 for s in suggestions)


@pytest.mark.asyncio
async def test_mark_availability_as_used(
    availability_service,
    mock_session
):
    """Test marking availability as used after scheduling"""
    # Setup
    availability_id = str(uuid.uuid4())
    availability = PlayerAvailability(
        id=availability_id,
        player_id=str(uuid.uuid4()),
        tournament_id=str(uuid.uuid4()),
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=2),
        availability_type=AvailabilityType.AVAILABLE,
        status=AvailabilityStatus.CONFIRMED
    )
    
    # Mock query
    mock_result = Mock()
    mock_result.first.return_value = availability
    mock_session.execute.return_value = mock_result
    
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    updated = await availability_service.mark_availability_as_used(
        availability_id=availability_id,
        session=mock_session
    )
    
    # Assert
    assert updated.status == AvailabilityStatus.SCHEDULED
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_old_availabilities(
    availability_service,
    mock_session
):
    """Test cleaning up old availability entries"""
    # Setup
    old_availabilities = [
        PlayerAvailability(
            id=str(uuid.uuid4()),
            player_id=str(uuid.uuid4()),
            tournament_id=str(uuid.uuid4()),
            start_time=datetime.now() - timedelta(days=30),
            end_time=datetime.now() - timedelta(days=30, hours=2),
            availability_type=AvailabilityType.AVAILABLE,
            status=AvailabilityStatus.EXPIRED
        )
        for _ in range(3)
    ]
    
    # Mock query
    mock_result = Mock()
    mock_result.all.return_value = old_availabilities
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    mock_session.delete = Mock()
    mock_session.commit = AsyncMock()
    
    # Execute
    deleted_count = await availability_service.cleanup_old_availabilities(
        older_than_days=30,
        session=mock_session
    )
    
    # Assert
    assert deleted_count == 3
    assert mock_session.delete.call_count == 3
    mock_session.commit.assert_called_once()