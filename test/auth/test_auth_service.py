"""Test suite for AuthService business logic"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import Optional

from auth.models import Player, Role, PlayerRole, Permission
from auth.schemas import (
    PlayerLogin, PlayerEmailCreate, TokenResponse, 
    PlayerStatus, AuthType, ScopeType    
)
from auth.service.permission import PermissionScope
from auth.service.auth import AuthService, create_auth_service
from auth.service.identity import IdentityService
from auth.service.permission import PermissionService
from auth.service.role import RoleService
from auth.service.status import PlayerStatusService
from auth.service.token import TokenService


@pytest.fixture
def mock_identity_service():
    """Mock IdentityService for testing"""
    mock = Mock(spec=IdentityService)
    mock.get_player_by_email = AsyncMock()
    mock.get_player_by_steam_id = AsyncMock()
    mock.verify_password = Mock(return_value=True)
    mock.hash_password = Mock(return_value="hashed_password")
    mock.verify_player = AsyncMock()
    mock.update_last_login = AsyncMock()
    return mock


@pytest.fixture
def mock_token_service():
    """Mock TokenService for testing"""
    mock = Mock(spec=TokenService)
    mock.create_access_token = Mock(return_value="access_token")
    mock.create_refresh_token = Mock(return_value="refresh_token")
    mock.decode_token = Mock()
    mock.validate_token = Mock()
    return mock


@pytest.fixture
def mock_permission_service():
    """Mock PermissionService for testing"""
    mock = Mock(spec=PermissionService)
    mock.check_permission = AsyncMock(return_value=True)
    mock.check_multiple_permissions = AsyncMock(return_value=True)
    mock.check_scoped_permission = AsyncMock(return_value=True)
    mock.get_player_permissions = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_role_service():
    """Mock RoleService for testing"""
    mock = Mock(spec=RoleService)
    mock.get_player_roles = AsyncMock(return_value=[])
    mock.add_player_to_role = AsyncMock()
    mock.remove_player_from_role = AsyncMock()
    mock.get_role_by_name = AsyncMock()
    return mock


@pytest.fixture
def mock_player_status_service():
    """Mock PlayerStatusService for testing"""
    mock = Mock(spec=PlayerStatusService)
    mock.check_player_active = AsyncMock(return_value=True)
    mock.update_player_status = AsyncMock()
    return mock


@pytest.fixture
def auth_service(
    mock_identity_service,
    mock_token_service,
    mock_permission_service,
    mock_role_service,
    mock_player_status_service
):
    """Create AuthService with mocked dependencies"""
    return AuthService(
        identity_service=mock_identity_service,
        token_service=mock_token_service,
        permission_service=mock_permission_service,
        role_service=mock_role_service,
        player_status_service=mock_player_status_service
    )


@pytest.fixture
def test_player():
    """Create a test player"""
    return Player(
        id="player123",
        email="test@example.com",
        password_hash="hashed_password",
        steam_id="76561198000000000",
        steam_name="TestPlayer",
        status=PlayerStatus.ACTIVE,
        auth_type=AuthType.EMAIL
    )


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.mark.asyncio
async def test_authenticate_player_valid_credentials(
    auth_service,
    mock_identity_service,
    mock_token_service,
    mock_player_status_service,
    test_player,
    mock_session
):
    """Test successful player authentication with valid credentials"""
    # Setup
    login_data = PlayerLogin(email="test@example.com", password="password123")
    mock_identity_service.get_player_by_email.return_value = test_player
    mock_identity_service.verify_password.return_value = True
    
    # Execute
    result = await auth_service.authenticate_player(login_data, mock_session)
    
    # Assert
    assert result is not None
    player, token_response = result
    assert player.id == test_player.id
    assert token_response.access_token == "access_token"
    assert token_response.refresh_token == "refresh_token"
    
    # Verify method calls
    mock_identity_service.get_player_by_email.assert_called_once_with(login_data.email, mock_session)
    mock_identity_service.verify_password.assert_called_once()
    mock_player_status_service.check_player_active.assert_called_once_with(test_player)
    mock_token_service.create_access_token.assert_called_once()
    mock_token_service.create_refresh_token.assert_called_once()


@pytest.mark.asyncio
async def test_authenticate_player_invalid_email(
    auth_service,
    mock_identity_service,
    mock_session
):
    """Test authentication fails with invalid email"""
    # Setup
    login_data = PlayerLogin(email="invalid@example.com", password="password123")
    mock_identity_service.get_player_by_email.return_value = None
    
    # Execute
    result = await auth_service.authenticate_player(login_data, mock_session)
    
    # Assert
    assert result is None
    mock_identity_service.get_player_by_email.assert_called_once()


@pytest.mark.asyncio
async def test_authenticate_player_invalid_password(
    auth_service,
    mock_identity_service,
    test_player,
    mock_session
):
    """Test authentication fails with invalid password"""
    # Setup
    login_data = PlayerLogin(email="test@example.com", password="wrong_password")
    mock_identity_service.get_player_by_email.return_value = test_player
    mock_identity_service.verify_password.return_value = False
    
    # Execute
    result = await auth_service.authenticate_player(login_data, mock_session)
    
    # Assert
    assert result is None
    mock_identity_service.verify_password.assert_called_once()


@pytest.mark.asyncio
async def test_authenticate_player_inactive_status(
    auth_service,
    mock_identity_service,
    mock_player_status_service,
    test_player,
    mock_session
):
    """Test authentication fails for inactive player"""
    # Setup
    login_data = PlayerLogin(email="test@example.com", password="password123")
    mock_identity_service.get_player_by_email.return_value = test_player
    mock_player_status_service.check_player_active.return_value = False
    
    # Execute
    result = await auth_service.authenticate_player(login_data, mock_session)
    
    # Assert
    assert result is None
    mock_player_status_service.check_player_active.assert_called_once_with(test_player)


@pytest.mark.asyncio
async def test_register_player_email(
    auth_service,
    mock_identity_service,
    mock_token_service,
    mock_role_service,
    mock_session
):
    """Test player registration with email"""
    # Setup
    registration_data = PlayerEmailCreate(
        email="new@example.com",
        password="password123",
        steam_id="76561198000000001",
        steam_name="NewPlayer"
    )
    
    new_player = Player(
        id="new_player_id",
        email=registration_data.email,
        password_hash="hashed_password",
        steam_id=registration_data.steam_id,
        steam_name=registration_data.steam_name,
        status=PlayerStatus.ACTIVE,
        auth_type=AuthType.EMAIL
    )
    
    default_role = Role(id="role123", name="player", permissions=["play"])
    
    mock_identity_service.get_player_by_email.return_value = None
    mock_identity_service.get_player_by_steam_id.return_value = None
    mock_identity_service.hash_password.return_value = "hashed_password"
    mock_role_service.get_role_by_name.return_value = default_role
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute with patched Player creation
    with patch('auth.service.auth.Player', return_value=new_player):
        result = await auth_service.register_player(registration_data, mock_session)
    
    # Assert
    assert result is not None
    player, token_response = result
    assert player.email == registration_data.email
    assert token_response.access_token == "access_token"
    
    # Verify method calls
    mock_identity_service.get_player_by_email.assert_called_once()
    mock_identity_service.get_player_by_steam_id.assert_called_once()
    mock_role_service.add_player_to_role.assert_called_once()


@pytest.mark.asyncio
async def test_register_player_duplicate_email(
    auth_service,
    mock_identity_service,
    test_player,
    mock_session
):
    """Test registration fails with duplicate email"""
    # Setup
    registration_data = PlayerEmailCreate(
        email="test@example.com",
        password="password123",
        steam_id="76561198000000002",
        steam_name="DuplicatePlayer"
    )
    
    mock_identity_service.get_player_by_email.return_value = test_player
    
    # Execute and assert
    with pytest.raises(ValueError, match="Email already registered"):
        await auth_service.register_player(registration_data, mock_session)


@pytest.mark.asyncio
async def test_register_player_duplicate_steam_id(
    auth_service,
    mock_identity_service,
    test_player,
    mock_session
):
    """Test registration fails with duplicate Steam ID"""
    # Setup
    registration_data = PlayerEmailCreate(
        email="new@example.com",
        password="password123",
        steam_id="76561198000000000",  # Same as test_player
        steam_name="DuplicatePlayer"
    )
    
    mock_identity_service.get_player_by_email.return_value = None
    mock_identity_service.get_player_by_steam_id.return_value = test_player
    
    # Execute and assert
    with pytest.raises(ValueError, match="Steam ID already registered"):
        await auth_service.register_player(registration_data, mock_session)


@pytest.mark.asyncio
async def test_refresh_access_token(
    auth_service,
    mock_identity_service,
    mock_token_service,
    mock_player_status_service,
    test_player,
    mock_session
):
    """Test refreshing access token with valid refresh token"""
    # Setup
    refresh_token = "valid_refresh_token"
    claims = {"sub": test_player.id, "type": "refresh"}
    
    mock_token_service.decode_token.return_value = claims
    mock_identity_service.get_player_by_id = AsyncMock(return_value=test_player)
    
    # Execute
    result = await auth_service.refresh_access_token(refresh_token, mock_session)
    
    # Assert
    assert result is not None
    player, token_response = result
    assert player.id == test_player.id
    assert token_response.access_token == "access_token"
    
    # Verify method calls
    mock_token_service.decode_token.assert_called_once_with(refresh_token)
    mock_player_status_service.check_player_active.assert_called_once_with(test_player)


@pytest.mark.asyncio
async def test_refresh_access_token_invalid_token_type(
    auth_service,
    mock_token_service,
    mock_session
):
    """Test refresh token fails with wrong token type"""
    # Setup
    refresh_token = "invalid_token"
    claims = {"sub": "player123", "type": "access"}  # Wrong type
    
    mock_token_service.decode_token.return_value = claims
    
    # Execute
    result = await auth_service.refresh_access_token(refresh_token, mock_session)
    
    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_check_player_permission(
    auth_service,
    mock_permission_service,
    test_player,
    mock_session
):
    """Test checking player permissions"""
    
    mock_permission_service.verify_permissions.return_value = True
    
    # Execute
    result = await auth_service.verify_permissions(
        test_player, 
        ["manage_teams"],
        PermissionScope(ScopeType.GLOBAL, None),
        mock_session
    )
    
    # Assert
    assert result is True
    mock_permission_service.verify_permissions.assert_called_once()


@pytest.mark.asyncio
async def test_check_player_scoped_permission(
    auth_service,
    mock_permission_service,
    test_player,
    mock_session
):
    """Test checking scoped permissions"""

    mock_permission_service.verify_permissions.return_value = True
    
    # Execute
    result = await auth_service.verify_permissions(
        test_player,
        ["manage_tournament"],
        PermissionScope(ScopeType.TOURNAMENT, "tournament123"),
        mock_session,
    )
    
    # Assert
    assert result is True
    mock_permission_service.verify_permissions.assert_called_once()


@pytest.mark.asyncio
async def test_create_auth_service_factory():
    """Test the create_auth_service factory function"""
    # Execute
    service = create_auth_service()
    
    # Assert
    assert isinstance(service, AuthService)
    assert service.identity_service is not None
    assert service.token_service is not None
    assert service.permission_service is not None
    assert service.role_service is not None
    assert service.player_status_service is not None


@pytest.mark.asyncio
async def test_update_last_login(
    auth_service,
    mock_identity_service,
    test_player,
    mock_session
):
    """Test updating player's last login timestamp"""
    # Setup
    mock_identity_service.update_last_login.return_value = test_player
    
    # Execute
    result = await auth_service.update_last_login(test_player, mock_session)
    
    # Assert
    assert result == test_player
    mock_identity_service.update_last_login.assert_called_once_with(test_player, mock_session)


@pytest.mark.asyncio
async def test_get_player_auth_info(
    auth_service,
    mock_permission_service,
    mock_role_service,
    test_player,
    mock_session
):
    """Test getting complete auth info for a player"""
    # Setup
    permissions = [
        Permission(id="perm1", name="play"),
        Permission(id="perm2", name="manage_team")
    ]
    roles = [
        Role(id="role1", name="player"),
        Role(id="role2", name="captain")
    ]
    
    mock_permission_service.get_player_permissions.return_value = permissions
    mock_role_service.get_player_roles.return_value = roles
    
    # Execute
    result = await auth_service.get_player_auth_info(test_player, mock_session)
    
    # Assert
    assert result["player_id"] == test_player.id
    assert result["permissions"] == [p.name for p in permissions]
    assert result["roles"] == [r.name for r in roles]
    assert result["status"] == test_player.status