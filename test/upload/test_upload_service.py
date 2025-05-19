"""Test suite for UploadService business logic"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, mock_open
from fastapi import UploadFile
import uuid
import os
import tempfile
import aiofiles

from upload.service import UploadService, UploadConfig
from upload.models import UploadRequest, UploadResult, UploadToken, UploadType
from state.service import StateService
from auth.models import Player


@pytest.fixture
def mock_state_service():
    """Mock StateService for testing"""
    mock = Mock(spec=StateService)
    mock.set_state = AsyncMock()
    mock.get_state = AsyncMock()
    mock.delete_state = AsyncMock()
    return mock


@pytest.fixture
def upload_service(mock_state_service):
    """Create UploadService with mocked dependencies"""
    return UploadService(state_service=mock_state_service)


@pytest.fixture
def test_player():
    """Create a test player"""
    return Player(
        id=str(uuid.uuid4()),
        steam_id="76561198000000000",
        steam_name="TestPlayer",
        email="test@example.com"
    )


@pytest.fixture
def test_upload_file():
    """Create a mock UploadFile"""
    file_content = b"fake image content"
    file = Mock(spec=UploadFile)
    file.filename = "test_logo.png"
    file.content_type = "image/png"
    file.size = len(file_content)
    file.read = AsyncMock(return_value=file_content)
    file.seek = AsyncMock()
    file.close = AsyncMock()
    return file


@pytest.fixture
def test_upload_request():
    """Create a test upload request"""
    return UploadRequest(
        upload_type=UploadType.TEAM_LOGO,
        filename="team_logo.png",
        content_type="image/png",
        size=5000,
        metadata={"team_id": str(uuid.uuid4())}
    )


@pytest.fixture
def test_upload_token():
    """Create a test upload token"""
    return UploadToken(
        token=str(uuid.uuid4()),
        upload_id=str(uuid.uuid4()),
        upload_type=UploadType.TEAM_LOGO,
        expires_at=datetime.now() + timedelta(minutes=15)
    )


def test_validate_upload_request_valid(upload_service, test_upload_request):
    """Test validating a valid upload request"""
    # Execute - should not raise exception
    upload_service.validate_upload_request(test_upload_request)


def test_validate_upload_request_invalid_type(upload_service):
    """Test validation fails for invalid upload type"""
    # Setup
    invalid_request = UploadRequest(
        upload_type="invalid_type",  # Invalid type
        filename="test.png",
        content_type="image/png",
        size=1000
    )
    
    # Execute and assert
    with pytest.raises(ValueError, match="Invalid upload type"):
        upload_service.validate_upload_request(invalid_request)


def test_validate_upload_request_invalid_content_type(upload_service):
    """Test validation fails for invalid content type"""
    # Setup
    invalid_request = UploadRequest(
        upload_type=UploadType.TEAM_LOGO,
        filename="test.exe",
        content_type="application/exe",  # Not allowed
        size=1000
    )
    
    # Execute and assert
    with pytest.raises(ValueError, match="Invalid content type"):
        upload_service.validate_upload_request(invalid_request)


def test_validate_upload_request_file_too_large(upload_service):
    """Test validation fails for oversized file"""
    # Setup
    invalid_request = UploadRequest(
        upload_type=UploadType.TEAM_LOGO,
        filename="test.png",
        content_type="image/png",
        size=10_000_000  # 10MB, exceeds 5MB limit
    )
    
    # Execute and assert
    with pytest.raises(ValueError, match="exceeds maximum"):
        upload_service.validate_upload_request(invalid_request)


@pytest.mark.asyncio
async def test_initiate_upload(upload_service, test_upload_request, test_player):
    """Test initiating an upload"""
    # Setup
    upload_id = str(uuid.uuid4())
    token = str(uuid.uuid4())
    
    with patch('uuid.uuid4', side_effect=[upload_id, token]):
        # Execute
        upload_token = await upload_service.initiate_upload(
            request=test_upload_request,
            player=test_player
        )
    
    # Assert
    assert upload_token.token == token
    assert upload_token.upload_id == upload_id
    assert upload_token.upload_type == test_upload_request.upload_type
    assert upload_token.player_id == test_player.id
    
    # Verify state was saved
    upload_service.state_service.set_state.assert_called_once()


@pytest.mark.asyncio
async def test_validate_upload_token_valid(upload_service, test_upload_token):
    """Test validating a valid upload token"""
    # Setup
    upload_state = {
        "upload_id": test_upload_token.upload_id,
        "upload_type": test_upload_token.upload_type.value,
        "expires_at": test_upload_token.expires_at.isoformat(),
        "used": False
    }
    upload_service.state_service.get_state.return_value = upload_state
    
    # Execute
    is_valid = await upload_service.validate_upload_token(test_upload_token.token)
    
    # Assert
    assert is_valid is True


@pytest.mark.asyncio
async def test_validate_upload_token_expired(upload_service, test_upload_token):
    """Test validation fails for expired token"""
    # Setup
    test_upload_token.expires_at = datetime.now() - timedelta(hours=1)
    upload_state = {
        "upload_id": test_upload_token.upload_id,
        "upload_type": test_upload_token.upload_type.value,
        "expires_at": test_upload_token.expires_at.isoformat(),
        "used": False
    }
    upload_service.state_service.get_state.return_value = upload_state
    
    # Execute
    is_valid = await upload_service.validate_upload_token(test_upload_token.token)
    
    # Assert
    assert is_valid is False


@pytest.mark.asyncio
async def test_validate_upload_token_already_used(upload_service, test_upload_token):
    """Test validation fails for already used token"""
    # Setup
    upload_state = {
        "upload_id": test_upload_token.upload_id,
        "upload_type": test_upload_token.upload_type.value,
        "expires_at": test_upload_token.expires_at.isoformat(),
        "used": True  # Already used
    }
    upload_service.state_service.get_state.return_value = upload_state
    
    # Execute
    is_valid = await upload_service.validate_upload_token(test_upload_token.token)
    
    # Assert
    assert is_valid is False


@pytest.mark.asyncio
async def test_process_upload(upload_service, test_upload_file, test_upload_token):
    """Test processing an upload"""
    # Setup
    upload_state = {
        "upload_id": test_upload_token.upload_id,
        "upload_type": test_upload_token.upload_type.value,
        "expires_at": test_upload_token.expires_at.isoformat(),
        "used": False,
        "metadata": {"team_id": str(uuid.uuid4())}
    }
    upload_service.state_service.get_state.return_value = upload_state
    
    # Mock file operations
    with patch('aiofiles.open', mock_open()) as mock_file:
        with patch('os.makedirs'):
            with patch('werkzeug.utils.secure_filename', return_value="test_logo.png"):
                # Execute
                result = await upload_service.process_upload(
                    file=test_upload_file,
                    token=test_upload_token.token
                )
    
    # Assert
    assert result.upload_id == test_upload_token.upload_id
    assert result.success is True
    assert result.filename == "test_logo.png"
    assert result.storage_path.startswith("/app/logo_store")
    
    # Verify state was updated
    assert upload_service.state_service.set_state.call_count == 2  # Token marked as used + result saved


@pytest.mark.asyncio
async def test_process_upload_invalid_token(upload_service, test_upload_file):
    """Test error when processing upload with invalid token"""
    # Setup
    upload_service.state_service.get_state.return_value = None
    
    # Execute and assert
    with pytest.raises(ValueError, match="Invalid upload token"):
        await upload_service.process_upload(
            file=test_upload_file,
            token="invalid-token"
        )


@pytest.mark.asyncio
async def test_get_upload_result(upload_service, test_upload_token):
    """Test getting upload result"""
    # Setup
    result_state = {
        "upload_id": test_upload_token.upload_id,
        "success": True,
        "filename": "test_logo.png",
        "storage_path": "/app/logo_store/test_logo.png",
        "content_type": "image/png",
        "size": 5000,
        "created_at": datetime.now().isoformat()
    }
    upload_service.state_service.get_state.return_value = result_state
    
    # Execute
    result = await upload_service.get_upload_result(test_upload_token.upload_id)
    
    # Assert
    assert result.upload_id == test_upload_token.upload_id
    assert result.success is True
    assert result.filename == "test_logo.png"


@pytest.mark.asyncio
async def test_cleanup_expired_tokens(upload_service):
    """Test cleaning up expired upload tokens"""
    # Setup
    expired_tokens = [
        f"upload:token:{uuid.uuid4()}",
        f"upload:token:{uuid.uuid4()}"
    ]
    
    # Mock state service to return expired tokens
    with patch.object(upload_service.state_service, 'scan_keys', return_value=expired_tokens):
        with patch.object(upload_service.state_service, 'get_state') as mock_get_state:
            # Set up expired token states
            mock_get_state.side_effect = [
                {
                    "expires_at": (datetime.now() - timedelta(hours=1)).isoformat(),
                    "used": False
                },
                {
                    "expires_at": (datetime.now() - timedelta(hours=2)).isoformat(),
                    "used": False
                }
            ]
            
            # Execute
            deleted_count = await upload_service.cleanup_expired_tokens()
    
    # Assert
    assert deleted_count == 2
    assert upload_service.state_service.delete_state.call_count == 2


@pytest.mark.asyncio
async def test_save_file(upload_service, test_upload_file):
    """Test saving file to disk"""
    # Setup
    save_path = "/tmp/test_logo.png"
    
    # Mock file operations
    with patch('aiofiles.open', mock_open()) as mock_file:
        with patch('os.makedirs'):
            # Execute
            saved_path = await upload_service.save_file(
                file=test_upload_file,
                save_path=save_path
            )
    
    # Assert
    assert saved_path == save_path
    mock_file.assert_called_once_with(save_path, 'wb')


@pytest.mark.asyncio
async def test_delete_file(upload_service):
    """Test deleting a file"""
    # Setup
    file_path = "/app/logo_store/old_logo.png"
    
    # Mock file operations
    with patch('os.path.exists', return_value=True):
        with patch('os.remove') as mock_remove:
            # Execute
            success = await upload_service.delete_file(file_path)
    
    # Assert
    assert success is True
    mock_remove.assert_called_once_with(file_path)


@pytest.mark.asyncio
async def test_delete_file_not_exists(upload_service):
    """Test deleting a non-existent file"""
    # Setup
    file_path = "/app/logo_store/non_existent.png"
    
    # Mock file operations
    with patch('os.path.exists', return_value=False):
        # Execute
        success = await upload_service.delete_file(file_path)
    
    # Assert
    assert success is False


@pytest.mark.asyncio
async def test_generate_unique_filename(upload_service):
    """Test generating unique filename"""
    # Setup
    original_filename = "team_logo.png"
    
    # Mock existing file check
    with patch('os.path.exists', side_effect=[True, True, False]):
        # Execute
        unique_filename = await upload_service.generate_unique_filename(
            directory="/app/logo_store",
            filename=original_filename
        )
    
    # Assert
    assert unique_filename != original_filename
    assert unique_filename.endswith(".png")
    assert "team_logo" in unique_filename


@pytest.mark.asyncio
async def test_validate_image_dimensions(upload_service, test_upload_file):
    """Test validating image dimensions"""
    # Setup
    max_width = 1920
    max_height = 1080
    
    # Mock PIL Image
    with patch('PIL.Image.open') as mock_image_open:
        mock_image = Mock()
        mock_image.size = (1280, 720)  # Valid dimensions
        mock_image_open.return_value = mock_image
        
        # Execute
        is_valid = await upload_service.validate_image_dimensions(
            file=test_upload_file,
            max_width=max_width,
            max_height=max_height
        )
    
    # Assert
    assert is_valid is True


@pytest.mark.asyncio
async def test_validate_image_dimensions_too_large(upload_service, test_upload_file):
    """Test validation fails for oversized image"""
    # Setup
    max_width = 1920
    max_height = 1080
    
    # Mock PIL Image
    with patch('PIL.Image.open') as mock_image_open:
        mock_image = Mock()
        mock_image.size = (3840, 2160)  # Too large
        mock_image_open.return_value = mock_image
        
        # Execute
        is_valid = await upload_service.validate_image_dimensions(
            file=test_upload_file,
            max_width=max_width,
            max_height=max_height
        )
    
    # Assert
    assert is_valid is False


@pytest.mark.asyncio
async def test_resize_image(upload_service, test_upload_file):
    """Test resizing an image"""
    # Mock PIL operations
    with patch('PIL.Image.open') as mock_image_open:
        mock_image = Mock()
        mock_resized = Mock()
        mock_image.resize.return_value = mock_resized
        mock_image_open.return_value = mock_image
        
        with patch('io.BytesIO') as mock_bytes_io:
            mock_buffer = Mock()
            mock_bytes_io.return_value = mock_buffer
            mock_buffer.getvalue.return_value = b"resized image data"
            
            # Execute
            resized_data = await upload_service.resize_image(
                file=test_upload_file,
                max_width=512,
                max_height=512
            )
    
    # Assert
    assert resized_data == b"resized image data"
    mock_image.resize.assert_called_once()
    mock_resized.save.assert_called_once()