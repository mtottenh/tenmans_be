import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from auth.models import Player, PlayerRole, Role
from auth.schemas import AuthType, PlayerEmailCreate, PlayerStatus, ScopeType
from status.transition_validator import TransitionError
from teams.models import Team, TeamCaptain
from teams.join_request.models import TeamJoinRequest
from teams.join_request.schemas import JoinRequestStatus
from competitions.models.seasons import Season, SeasonState
from auth.models import Permission
from services.auth import auth_service
from services.team import team_service
from services.team_join_request import join_request_service
from services.role import role_service
from services.season import season_service
from services.permission import permission_service

# Test cases
@pytest.mark.asyncio
async def test_duplicate_join_requests(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_team_and_captain: Tuple[Team, Player],
    test_season: Season
):
    """Test that players cannot submit duplicate join requests"""
    team, _ = test_team_and_captain
    player = test_players['another_user']
    
    # Submit first request
    await join_request_service.create_request(
        player=player,
        team=team,
        season=test_season,
        message="First request",
        actor=player,
        session=session
    )
    
    # Attempt duplicate request
    with pytest.raises(ValueError, match="already has a pending request"):
        await join_request_service.create_request(
            player=player,
            team=team,
            season=test_season,
            message="Second request",
            actor=player,
            session=session
        )

@pytest.mark.asyncio
async def test_captain_approve_request(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_team_and_captain: Tuple[Team, Player],
    test_season: Season
):
    """Test that team captains can approve join requests"""
    team, captain = test_team_and_captain
    player = test_players['another_user']
    
    # Create request
    request = await join_request_service.create_request(
        player=player,
        team=team,
        season=test_season,
        message="Please let me join",
        actor=player,
        session=session
    )
    
    # Captain approves request
    await join_request_service.approve_request(
        request=request,
        captain=captain,
        response_message="Welcome!",
        actor=captain,
        session=session
    )
    
    # Verify request status
    request = await join_request_service.get_request_by_id(request.id, session)
    assert request.status == JoinRequestStatus.APPROVED

@pytest.mark.asyncio
async def test_non_captain_cannot_approve(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_team_and_captain: Tuple[Team, Player],
    test_season: Season
):
    """Test that non-captains cannot approve join requests"""
    team, _ = test_team_and_captain
    player = test_players['another_user']
    
    
    # Create request
    request = await join_request_service.create_request(
        player=player,
        team=team,
        season=test_season,
        message="Please let me join",
        actor=player,
        session=session
    )
    
    # Attempt approval by non-captain
    with pytest.raises(TransitionError, match="Only team captains can"):
        await join_request_service.approve_request(
            request=request,
            captain=player,
            response_message="Welcome!",
            actor=player,
            session=session
        )

@pytest.mark.asyncio
async def test_captain_reject_request(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_team_and_captain: Tuple[Team, Player],
    test_season: Season
):
    """Test that team captains can reject join requests"""
    team, captain = test_team_and_captain
    player = test_players['another_user']
    
    # Create request
    request = await join_request_service.create_request(
        player=player,
        team=team,
        season=test_season,
        message="Please let me join",
        actor=player,
        session=session
    )
    
    # Captain rejects request
    await join_request_service.reject_request(
        request=request,
        captain=captain,
        response_message="Sorry, team is full",
        actor=captain,
        session=session
    )
    
    # Verify request status
    request = await join_request_service.get_request_by_id(request.id, session)
    assert request.status == JoinRequestStatus.REJECTED

@pytest.mark.asyncio
async def test_player_cancel_request(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_team_and_captain: Tuple[Team, Player],
    test_season: Season
):
    """Test that players can cancel their own join requests"""
    team, _ = test_team_and_captain
    player = test_players['another_user']
    
    # Create request
    request = await join_request_service.create_request(
        player=player,
        team=team,
        season=test_season,
        message="Please let me join",
        actor=player,
        session=session
    )
    
    # Player cancels request
    await join_request_service.cancel_request(
        request=request,
        player=player,
        actor=player,
        session=session
    )
    
    # Verify request status
    request = await join_request_service.get_request_by_id(request.id, session)
    assert request.status == JoinRequestStatus.CANCELLED

@pytest.mark.asyncio
async def test_other_player_cannot_cancel(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_team_and_captain: Tuple[Team, Player],
    test_season: Season
):
    """Test that other players cannot cancel someone else's request"""
    team, _ = test_team_and_captain
    player = test_players['another_user']
    other_player = test_players['regular_user']
    
    # Create request
    request = await join_request_service.create_request(
        player=player,
        team=team,
        season=test_season,
        message="Please let me join",
        actor=player,
        session=session
    )
    
    # Attempt cancellation by other player
    with pytest.raises(TransitionError, match="Only the requesting player"):
        await join_request_service.cancel_request(
            request=request,
            player=other_player,
            actor=other_player,
            session=session
        )

@pytest.mark.asyncio
async def test_admin_cleanup_expired(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_team_and_captain: Tuple[Team, Player],
    test_season: Season
):
    """Test that admins can clean up expired requests"""
    team, _ = test_team_and_captain
    player = test_players['another_user']
    
    # Create request with old timestamp
    request = await join_request_service.create_request(
        player=player,
        team=team,
        season=test_season,
        message="Old request",
        actor=player,
        session=session
    )
    
    # Manually update timestamp to be old
    request.created_at = datetime.now() - timedelta(days=10)
    session.add(request)
    await session.commit()
    
    # Run cleanup
    expired_count = await join_request_service.cleanup_expired_requests(
        session=session,
        expiry_days=7
    )
    
    assert expired_count == 1
    
    # Verify request status
    request = await join_request_service.get_request_by_id(request.id, session)
    assert request.status == JoinRequestStatus.EXPIRED