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

# Initialize standard permissions that match the production system
async def init_permissions(session: AsyncSession) -> Dict[str, Permission]:
    """Initialize standard system permissions"""
    permissions = {}
    
    # Base user permissions
    base_perms = [
        ("user", "Basic user access"),
        ("view_tournaments", "View tournament information"),
        ("join_tournaments", "Join tournaments"),
        ("view_teams", "View team information"),
        ("join_teams", "Join teams"),
        ("submit_results", "Submit match results"),
        ("view_matches", "View match information")
    ]
    
    # Team management permissions
    team_perms = [
        ("manage_team", "Manage team settings"),
        ("manage_roster", "Manage team roster"),
        ("schedule_matches", "Schedule team matches"),
        ("confirm_results", "Confirm match results")
    ]
    
    # Tournament management permissions
    tournament_perms = [
        ("manage_tournament", "Manage tournament settings"),
        ("manage_fixtures", "Manage tournament fixtures"),
        ("manage_results", "Manage tournament results"),
        ("manage_participants", "Manage tournament participants"),
        ("verify_results", "Verify match results")
    ]
    
    # Global admin permissions
    admin_perms = [
        ("admin", "Global administrative access"),
        ("moderate_chat", "Moderate chat"),
        ("manage_bans", "Manage user bans"),
        ("verify_users", "Verify user accounts"),
        ("manage_reports", "Manage user reports"),
        ("manage_seasons", "Manage seasons"),
        ("manage_tournaments", "Manage all tournaments"),
        ("manage_teams", "Manage all teams"),
        ("manage_users", "Manage user accounts"),
        ("manage_roles", "Manage roles and permissions"),
        ("manage_maps", "Manage map pool")
    ]
    
    # Create all permissions
    all_perms = base_perms + team_perms + tournament_perms + admin_perms
    sys_user = await get_or_create_system_user(session)
    for perm_name, description in all_perms:
        if not await permission_service.get_permission_by_name(perm_name, session):
            perm = await permission_service.create_permission(
                name=perm_name,
                description=description,
                actor=sys_user,
                session=session
            )
            permissions[perm_name] = perm

    return permissions

async def get_or_create_system_user(session: AsyncSession) -> Player:
    """Get or create the SYSTEM user with admin privileges"""
    system_user = await auth_service.get_player_by_name("SYSTEM", session)
    if not system_user:
        # Create SYSTEM user
        system_user = Player(
            name="SYSTEM",
            steam_id="76561197971721555",  # Special value for system user
            auth_type=AuthType.STEAM,
            status=PlayerStatus.ACTIVE
        )
        session.add(system_user)
        await session.commit()
    return system_user

@pytest_asyncio.fixture
async def system_user(session: AsyncSession) -> Player:
    """Fixture to ensure SYSTEM user exists"""
    return await get_or_create_system_user(session)

@pytest_asyncio.fixture
async def test_permissions(session: AsyncSession, system_user: Player) -> Dict[str, Permission]:
    """Initialize all system permissions"""
    return await init_permissions(session)

@pytest_asyncio.fixture
async def test_roles(
    session: AsyncSession,
    system_user: Player,
    test_permissions: Dict[str, Permission]
) -> Dict[str, Role]:
    """Create standard roles with appropriate permissions"""
    roles = {}
    
    # Get all permissions
    user_perms = [
        "user", "view_tournaments", "join_tournaments",
        "view_teams", "join_teams", "submit_results", "view_matches"
    ]
    
    captain_perms = [
        "manage_team", "manage_roster", "schedule_matches",
        "confirm_results"
    ]
    
    admin_perms = [
        "admin", "moderate_chat", "manage_bans", "verify_users",
        "manage_reports", "manage_seasons", "manage_tournaments",
        "manage_teams", "manage_users", "manage_roles", "manage_maps"
    ]
    
    # Create user role
    if not await role_service.get_role_by_name("user", session):
        user_role = await role_service.create_role(
            name="user",
            permission_ids=[test_permissions[p].id for p in user_perms],
            actor=system_user,
            session=session
        )
        roles['user'] = user_role
    
    # Create team captain role
    if not await role_service.get_role_by_name("team_captain", session):
        captain_role = await role_service.create_role(
            name="team_captain",
            permission_ids=[test_permissions[p].id for p in captain_perms],
            actor=system_user,
            session=session
        )
        roles['team_captain'] = captain_role
    
    # Create admin role
    if not await role_service.get_role_by_name("admin", session):
        admin_role = await role_service.create_role(
            name="admin",
            permission_ids=[test_permissions[p].id for p in admin_perms],
            actor=system_user,
            session=session
        )
        roles['admin'] = admin_role
    sys_user = await get_or_create_system_user(session)
    await role_service.assign_role(player=sys_user, role=roles['admin'], scope_type=ScopeType.GLOBAL, scope_id=None, actor=sys_user, session=session)
    return roles

@pytest_asyncio.fixture
async def test_players(
    session: AsyncSession,
    system_user: Player,
    test_roles: Dict[str, Role]
) -> Dict[str, Player]:
    """Create test players with different role combinations"""
    players = {'system': system_user}
    
    # Create regular player
    regular_user = await auth_service.create_player_with_email(
        PlayerEmailCreate(name="regular_user",email="regular_user@gmail.com", password="abcdefgg1234",steam_id="12345789",submitted_evidence=".."),
        actor=system_user,
        session=session
    )
    await role_service.assign_role(
        regular_user,
        test_roles['user'],
        ScopeType.GLOBAL,
        None,
        actor=system_user,
        session=session
    )
    players['regular_user'] = regular_user
    
    # Create another regular player
    another_user = await auth_service.create_player_with_email(
        PlayerEmailCreate(name="another_user",email="another_user@gmail.com", password="abcdefg1234",steam_id="12345",submitted_evidence=".."),
        actor=system_user,
        session=session
    )
    await role_service.assign_role(
        another_user,
        test_roles['user'],
        ScopeType.GLOBAL,
        None,
        actor=system_user,
        session=session
    )
    players['another_user'] = another_user
    
    # Create admin player
    admin_user = await auth_service.create_player_with_email(
       PlayerEmailCreate(name="admin_user",email="admin_user@gmail.com", password="abcdefgg1234",steam_id="123097845",submitted_evidence=".."),
        actor=system_user,
        session=session
    )
    await role_service.assign_role(
        admin_user,
        test_roles['admin'],
        ScopeType.GLOBAL,
        None,
        actor=system_user,
        session=session
    )
    players['admin'] = admin_user
    
    return players

@pytest_asyncio.fixture
async def test_season(session: AsyncSession, system_user: Player) -> Season:
    """Create an active test season"""
    from competitions.schemas import SeasonCreate
    season = await season_service.create_season(
       season=SeasonCreate(name="Test Season"),
        session=session
    )
    await season_service.start_season(season.id, session)
    return season

@pytest_asyncio.fixture
async def test_team_and_captain(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_roles: Dict[str, Role],
    test_season: Season,
    system_user: Player
) -> Tuple[Team, Player]:
    """Create a test team with a captain"""
    # Create team with regular_user as captain
    team = await team_service.create_team(
        name="Test Team",
        captain=test_players['regular_user'],
        actor=test_players['regular_user'],
        logo_path=None,
        session=session
    )
    
    # # Assign captain role with team scope
    # await role_service.assign_role(
    #     test_players['regular_user'],
    #     test_roles['team_captain'],
    #     ScopeType.TEAM,
    #     team.id,
    #     actor=system_user,
    #     session=session
    # )
    
    return team, test_players['regular_user']
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