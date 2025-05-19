import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import Dict, List, Tuple
from datetime import datetime, timedelta

from auth.models import Player, Role
from auth.schemas import AuthType, PlayerStatus, ScopeType
from auth.service.permission import PermissionScope
from teams.models import Team, TeamCaptain
from teams.base_schemas import TeamStatus, RosterStatus, TeamCaptainStatus
from competitions.models.seasons import Season, SeasonState
from competitions.models.tournaments import Tournament, TournamentState
from competitions.models.fixtures import Fixture, FixtureStatus

from services.auth import auth_service
from services.team import team_service
from services.season import season_service
from services.tournament import tournament_service
from services.fixture import fixture_service
from services.role import role_service

@pytest_asyncio.fixture
async def test_team_with_members(
    session: AsyncSession,
    test_players: Dict[str, Player],
    test_roles: Dict[str, Role],
    test_season: Season,
    system_user: Player
) -> Tuple[Team, List[Player]]:
    """Create a test team with multiple members"""
    # Create team with one captain
    team = await team_service.create_team(
        name="Test Team",
        captain=test_players['regular_user'],
        actor=test_players['regular_user'],
        logo_path=None,
        session=session
    )
    
    # Add additional players to the team
    members = [test_players['another_user']]  # Add more test players if needed
    for player in members:
        await team_service.add_player_to_roster(
            team=team,
            player=player,
            season=test_season,
            actor=test_players['regular_user'],
            session=session
        )
    session.refresh(team)

    return team, [test_players['regular_user']] + members

@pytest_asyncio.fixture
async def test_tournament_with_team(
    session: AsyncSession,
    test_team_with_members: Tuple[Team, List[Player]],
    test_season: Season,
    system_user: Player
) -> Tournament:
    """Create a test tournament with the team registered"""
    team, _ = test_team_with_members
    
    # Create tournament
    tournament = await tournament_service.create_tournament(
        tournament_data={
            "name": "Test Tournament",
            "season_id": test_season.id,
            "type": "regular",
            "registration_start": datetime.now() - timedelta(days=1),
            "registration_end": datetime.now() + timedelta(days=1),
            "scheduled_start": datetime.now() + timedelta(days=2),
            "scheduled_end": datetime.now() + timedelta(days=30),
            "max_team_size": 7,
            "map_pool": [],
            "format_config": {
                "teams_per_group": 4,
                "match_format": "bo3"
            }
        },
        actor=system_user,
        session=session
    )
    
    # Register team
    await tournament_service.request_registration(
        registration={
            "team_id": team.id,
            "notes": "Test registration",
            "requested_by": system_user.id,
            "requested_at": datetime.now(),
            "tournament_id": tournament.id
        },
        actor=system_user,
        session=session
    )
    
    return tournament

@pytest.mark.asyncio
async def test_captain_can_disband_team(
    session: AsyncSession,
    test_team_with_members: Tuple[Team, List[Player]]
):
    """Test that a team captain can disband their team"""
    team, members = test_team_with_members
    captain = members[0]  # First member is the captain
    
    # Captain disbands team
    await team_service.disband_team(
        team=team,
        reason="Testing team disbanding",
        actor=captain,
        session=session
    )
    
    # Verify team status
    await session.refresh(team)
    assert team.status == TeamStatus.DISBANDED
    assert team.disbanded_at is not None
    assert team.disbanded_by == captain.id
    
    # Verify captain status
    captain_entry = await team_service.get_captain(team, captain, session)
    assert captain_entry.status == TeamCaptainStatus.DISBANDED
    
    # Verify roster statuses
    for member in members:
        roster = await team_service.get_team_roster(team, member, session)
        assert roster.status == RosterStatus.PAST

@pytest.mark.asyncio
async def test_non_captain_cannot_disband_team(
    session: AsyncSession,
    test_team_with_members: Tuple[Team, List[Player]]
):
    """Test that non-captains cannot disband the team"""
    team, members = test_team_with_members
    non_captain = members[1]  # Second member is not a captain
    
    # Attempt disband by non-captain should fail
    with pytest.raises(ValueError, match="Only team captains"):
        await team_service.disband_team(
            team=team,
            reason="Testing unauthorized disbanding",
            actor=non_captain,
            session=session
        )
    
    # Verify team status hasn't changed
    await session.refresh(team)
    assert team.status == TeamStatus.ACTIVE

@pytest.mark.asyncio
async def test_admin_can_disband_team(
    session: AsyncSession,
    test_team_with_members: Tuple[Team, List[Player]],
    test_players: Dict[str, Player]
):
    """Test that an admin can disband any team"""
    team, _ = test_team_with_members
    admin = test_players['admin']
    
    # Admin disbands team
    await team_service.disband_team(
        team=team,
        reason="Admin disbanding test",
        actor=admin,
        session=session
    )
    
    # Verify team status
    await session.refresh(team)
    assert team.status == TeamStatus.DISBANDED
    assert team.disbanded_at is not None
    assert team.disbanded_by == admin.id

@pytest.mark.asyncio
async def test_disbanding_affects_tournament_registration(
    session: AsyncSession,
    test_team_with_members: Tuple[Team, List[Player]],
    test_tournament_with_team: Tournament
):
    """Test that disbanding a team affects tournament registrations"""
    team, members = test_team_with_members
    captain = members[0]
    
    # Disband team
    await team_service.disband_team(
        team=team,
        reason="Testing tournament effects",
        actor=captain,
        session=session
    )
    
    # Verify tournament registration status
    registration = await tournament_service.get_registration(
        tournament_id=test_tournament_with_team.id,
        team_id=team.id,
        session=session
    )
    assert registration.status == "withdrawn"  # Or whatever status your system uses

@pytest.mark.asyncio
async def test_disbanded_team_permissions(
    session: AsyncSession,
    test_team_with_members: Tuple[Team, List[Player]]
):
    """Test that disbanded team permissions are properly revoked"""
    team, members = test_team_with_members
    captain = members[0]
    
    # Disband team
    await team_service.disband_team(
        team=team,
        reason="Testing permission revocation",
        actor=captain,
        session=session
    )
    
    # Verify captain loses team management permissions
    has_permission = await auth_service.verify_permissions(
        player=captain,
        required_permissions=["manage_team"],
        scope=PermissionScope(ScopeType.TEAM, team.id),
        session=session
    )
    assert not has_permission

@pytest.mark.asyncio
async def test_disbanding_with_active_matches(
    session: AsyncSession,
    test_team_with_members: Tuple[Team, List[Player]],
    test_tournament_with_team: Tournament
):
    """Test disbanding a team with active matches"""
    team, members = test_team_with_members
    captain = members[0]
    
    # Create an active match
    fixture = await fixture_service.create_fixture(
        tournament_id=test_tournament_with_team.id,
        team_1=team.id,
        team_2=test_tournament_with_team.teams[1].id,  # Another team
        scheduled_at=datetime.now() + timedelta(days=1),
        session=session
    )
    
    # Disband team
    await team_service.disband_team(
        team=team,
        reason="Testing match effects",
        actor=captain,
        session=session
    )
    
    # Verify fixture status
    await session.refresh(fixture)
    assert fixture.status == FixtureStatus.FORFEITED  # Or appropriate status
    assert fixture.forfeit_winner == fixture.team_2  # Other team wins by forfeit

@pytest.mark.asyncio
async def test_prevent_rejoining_disbanded_team(
    session: AsyncSession,
    test_team_with_members: Tuple[Team, List[Player]],
    test_players: Dict[str, Player]
):
    """Test that players cannot join a disbanded team"""
    team, members = test_team_with_members
    captain = members[0]
    new_player = test_players['another_user']
    
    # Disband team
    await team_service.disband_team(
        team=team,
        reason="Testing join prevention",
        actor=captain,
        session=session
    )
    
    # Attempt to add new player should fail
    with pytest.raises(ValueError, match="Cannot join disbanded team"):
        await team_service.add_player_to_roster(
            team=team,
            player=new_player,
            season=test_season,
            actor=captain,
            session=session
        )