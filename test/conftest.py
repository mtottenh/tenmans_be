from typing import Dict, Tuple
import pytest
import pytest_asyncio
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import DropTable
from sqlalchemy.ext.compiler import compiles
from sqlmodel import SQLModel
from auth.models import Permission, Player, Role
from auth.schemas import AuthType, PlayerEmailCreate, PlayerStatus, ScopeType
from competitions.models.seasons import Season
from db.main import get_session
from config import Config
import logging
from services.auth import auth_service
from services.team import team_service
from services.role import role_service
from services.permission import permission_service
from services.season import season_service
from teams.models import Team

# Import all models to ensure they're registered with SQLModel metadata
# This is necessary for create_all to work properly
from competitions.models.tournaments import Tournament, TournamentRegistration
from competitions.models.rounds import Round
from competitions.models.fixtures import Fixture
from competitions.models.linked_tournaments import LinkedTournament
from competitions.map_pool.models import TournamentMapPool, MapPoolMap, MapPoolVote 
from matches.models import MatchPlayer, Result
from matches.evidence.models import MatchEvidence, EvidenceConfirmation
from teams.join_request.models import TeamJoinRequest
from maps.models import Map
from audit.models import AuditEvent
from substitutes.models import SubstituteAvailability
from pugs.models import PugPlayer, Pug
from moderation.models import Ban

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add CASCADE to DROP TABLE statements
@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return compiler.visit_drop_table(element) + " CASCADE"

# Event loop fixture
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Test database URL
TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{Config.POSTGRES_USER}:{Config.POSTGRES_PASSWORD}@db/{Config.POSTGRES_DB}"
)

@pytest.fixture(scope="session")
def test_engine():
    """Create a test engine fixture."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT"  # This can help with transaction management
    )
    yield engine

@pytest_asyncio.fixture(scope="function")
async def prepare_test_database(test_engine):
    """Initialize database for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    
    try:
        yield
    finally:
        # Clean up after test
        async with test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)

# Session fixture
@pytest_asyncio.fixture
async def session(test_engine, prepare_test_database):
    """Provide an async session for testing."""
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )
    
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

# Override FastAPI dependencies for testing
@pytest.fixture(autouse=True)
def override_dependencies():
    from main import app

    async def get_test_session():
        async_session = sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        async with async_session() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[get_session] = get_test_session
    yield
    app.dependency_overrides.clear()

# Admin user fixture
@pytest_asyncio.fixture
async def admin_user(session, test_roles, system_user):
    from auth.models import Player, AuthType, PlayerStatus
    from auth.schemas import ScopeType
    admin = Player(
        name="Test Admin",
        steam_id="76561197971721556",
        auth_type=AuthType.STEAM,
        status=PlayerStatus.ACTIVE
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    
    # Assign admin role to give the test admin proper permissions
    await role_service.assign_role(
        admin,
        test_roles['admin'],
        ScopeType.GLOBAL,
        None,
        actor=system_user,
        session=session
    )
    
    return admin


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
        PlayerEmailCreate(name="regular_user",email="regular_user@gmail.com", password="abcdefgg1234",steam_id="12345789",submitted_evidence=None),
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
        PlayerEmailCreate(name="another_user",email="another_user@gmail.com", password="abcdefg1234",steam_id="12345",submitted_evidence=None),
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
       PlayerEmailCreate(name="admin_user",email="admin_user@gmail.com", password="abcdefgg1234",steam_id="123097845",submitted_evidence=None),
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
    
    # Create additional players for team tests requiring 5+ members
    for i in range(3, 8):  # Create players 3 through 7
        extra_player = await auth_service.create_player_with_email(
            PlayerEmailCreate(
                name=f"player_{i}",
                email=f"player_{i}@gmail.com",
                password="abcdefgg1234",
                steam_id=f"1000000{i}",
                submitted_evidence=None
            ),
            actor=system_user,
            session=session
        )
        await role_service.assign_role(
            extra_player,
            test_roles['user'],
            ScopeType.GLOBAL,
            None,
            actor=system_user,
            session=session
        )
        players[f'player_{i}'] = extra_player
    
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