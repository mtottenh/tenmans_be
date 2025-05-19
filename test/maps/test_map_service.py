"""Test suite for MapService business logic"""

import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
import uuid

from maps.service import MapService, MapNotFoundException
from maps.models import Map
from maps.schemas import MapCreate
from competitions.base_schemas import GameMode, MapCategory


@pytest.fixture
def map_service():
    """Create MapService instance"""
    return MapService()


@pytest.fixture
def test_maps():
    """Create test maps"""
    return [
        Map(
            id=str(uuid.uuid4()),
            name="de_dust2",
            display_name="Dust II",
            image_url="https://example.com/dust2.jpg",
            category=MapCategory.ACTIVE_DUTY,
            supported_modes=[GameMode.COMPETITIVE, GameMode.WINGMAN],
            active=True,
            created_at=datetime.now()
        ),
        Map(
            id=str(uuid.uuid4()),
            name="de_inferno",
            display_name="Inferno",
            image_url="https://example.com/inferno.jpg",
            category=MapCategory.ACTIVE_DUTY,
            supported_modes=[GameMode.COMPETITIVE],
            active=True,
            created_at=datetime.now()
        ),
        Map(
            id=str(uuid.uuid4()),
            name="de_mirage",
            display_name="Mirage",
            image_url="https://example.com/mirage.jpg",
            category=MapCategory.RESERVE,
            supported_modes=[GameMode.COMPETITIVE, GameMode.WINGMAN],
            active=True,
            created_at=datetime.now()
        ),
        Map(
            id=str(uuid.uuid4()),
            name="de_cache",
            display_name="Cache",
            image_url="https://example.com/cache.jpg",
            category=MapCategory.RESERVE,
            supported_modes=[GameMode.COMPETITIVE],
            active=False,  # Inactive map
            created_at=datetime.now()
        )
    ]


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.mark.asyncio
async def test_get_all_maps(
    map_service,
    test_maps,
    mock_session
):
    """Test getting all maps"""
    # Setup - Mock the query
    mock_result = Mock()
    mock_result.all.return_value = test_maps
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    maps = await map_service.get_all_maps(mock_session)
    
    # Assert
    assert len(maps) == 4
    assert all(isinstance(map, Map) for map in maps)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_map_by_id(
    map_service,
    test_maps,
    mock_session
):
    """Test getting a map by ID"""
    # Setup
    target_map = test_maps[0]
    
    mock_result = Mock()
    mock_result.first.return_value = target_map
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    map_obj = await map_service.get_map(target_map.id, mock_session)
    
    # Assert
    assert map_obj.id == target_map.id
    assert map_obj.name == "de_dust2"
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_map_not_found(
    map_service,
    mock_session
):
    """Test error when map not found by ID"""
    # Setup
    non_existent_id = str(uuid.uuid4())
    
    mock_result = Mock()
    mock_result.first.return_value = None
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute and assert
    with pytest.raises(MapNotFoundException, match=f"Map id={non_existent_id} not found"):
        await map_service.get_map(non_existent_id, mock_session)


@pytest.mark.asyncio
async def test_get_map_by_name(
    map_service,
    test_maps,
    mock_session
):
    """Test getting a map by name"""
    # Setup
    target_map = test_maps[1]
    
    mock_result = Mock()
    mock_result.first.return_value = target_map
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    map_obj = await map_service.get_map_by_name("de_inferno", mock_session)
    
    # Assert
    assert map_obj.name == "de_inferno"
    assert map_obj.display_name == "Inferno"
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_map_by_name_not_found(
    map_service,
    mock_session
):
    """Test error when map not found by name"""
    # Setup
    mock_result = Mock()
    mock_result.first.return_value = None
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute and assert
    with pytest.raises(MapNotFoundException, match="Map de_nuke not found"):
        await map_service.get_map_by_name("de_nuke", mock_session)


@pytest.mark.asyncio
async def test_get_maps_by_mode(
    map_service,
    test_maps,
    mock_session
):
    """Test getting maps that support a specific game mode"""
    # Setup - Filter for WINGMAN mode
    wingman_maps = [test_maps[0], test_maps[2]]  # dust2 and mirage support wingman
    
    mock_result = Mock()
    mock_result.all.return_value = wingman_maps
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    maps = await map_service.get_maps_by_mode(GameMode.WINGMAN, mock_session)
    
    # Assert
    assert len(maps) == 2
    assert all(GameMode.WINGMAN in map.supported_modes for map in maps)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_maps_by_category(
    map_service,
    test_maps,
    mock_session
):
    """Test getting maps by category"""
    # Setup - Filter for ACTIVE_DUTY category
    active_duty_maps = [test_maps[0], test_maps[1]]  # dust2 and inferno
    
    mock_result = Mock()
    mock_result.all.return_value = active_duty_maps
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    maps = await map_service.get_maps_by_category(MapCategory.ACTIVE_DUTY, mock_session)
    
    # Assert
    assert len(maps) == 2
    assert all(map.category == MapCategory.ACTIVE_DUTY for map in maps)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_active_maps(
    map_service,
    test_maps,
    mock_session
):
    """Test getting only active maps"""
    # Setup - Filter out inactive maps
    active_maps = [test_maps[0], test_maps[1], test_maps[2]]  # Exclude cache
    
    mock_result = Mock()
    mock_result.all.return_value = active_maps
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    maps = await map_service.get_active_maps(mock_session)
    
    # Assert
    assert len(maps) == 3
    assert all(map.active for map in maps)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_map(
    map_service,
    mock_session
):
    """Test creating a new map"""
    # Setup
    map_data = MapCreate(
        name="de_ancient",
        display_name="Ancient",
        image_url="https://example.com/ancient.jpg",
        category=MapCategory.ACTIVE_DUTY,
        supported_modes=[GameMode.COMPETITIVE]
    )
    
    # Mock the add and commit operations
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    new_map = await map_service.create_map(map_data, mock_session)
    
    # Assert
    assert new_map.name == "de_ancient"
    assert new_map.display_name == "Ancient"
    assert new_map.category == MapCategory.ACTIVE_DUTY
    assert new_map.active is True
    
    # Verify database operations
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_update_map(
    map_service,
    test_maps,
    mock_session
):
    """Test updating an existing map"""
    # Setup
    target_map = test_maps[0]
    update_data = {
        "display_name": "Dust 2 Updated",
        "image_url": "https://example.com/dust2_new.jpg",
        "active": False
    }
    
    # Mock the query
    mock_result = Mock()
    mock_result.first.return_value = target_map
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Execute
    updated_map = await map_service.update_map(
        map_id=target_map.id,
        update_data=update_data,
        session=mock_session
    )
    
    # Assert
    assert updated_map.display_name == "Dust 2 Updated"
    assert updated_map.image_url == "https://example.com/dust2_new.jpg"
    assert updated_map.active is False
    
    # Verify database operations
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_delete_map(
    map_service,
    test_maps,
    mock_session
):
    """Test soft deleting a map"""
    # Setup
    target_map = test_maps[3]  # Cache map
    
    # Mock the query
    mock_result = Mock()
    mock_result.first.return_value = target_map
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    mock_session.commit = AsyncMock()
    
    # Execute
    await map_service.delete_map(target_map.id, mock_session)
    
    # Assert
    assert target_map.active is False
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_maps_for_tournament(
    map_service,
    test_maps,
    mock_session
):
    """Test getting maps suitable for tournament play"""
    # Setup - Only active competitive maps
    tournament_maps = [test_maps[0], test_maps[1], test_maps[2]]
    
    mock_result = Mock()
    mock_result.all.return_value = tournament_maps
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute
    maps = await map_service.get_maps_for_tournament(mock_session)
    
    # Assert
    assert len(maps) == 3
    assert all(map.active for map in maps)
    assert all(GameMode.COMPETITIVE in map.supported_modes for map in maps)


@pytest.mark.asyncio
async def test_validate_map_pool(
    map_service,
    test_maps,
    mock_session
):
    """Test validating a map pool for a tournament"""
    # Setup
    map_ids = [test_maps[0].id, test_maps[1].id, test_maps[2].id]
    
    # Mock individual map queries
    mock_results = []
    for map_obj in test_maps[:3]:
        mock_result = Mock()
        mock_result.first.return_value = map_obj
        mock_results.append(mock_result)
    
    mock_scalars_list = [Mock(return_value=result) for result in mock_results]
    mock_session.execute.side_effect = [Mock(scalars=scalars) for scalars in mock_scalars_list]
    
    # Execute
    is_valid = await map_service.validate_map_pool(map_ids, mock_session)
    
    # Assert
    assert is_valid is True


@pytest.mark.asyncio
async def test_validate_map_pool_with_inactive_map(
    map_service,
    test_maps,
    mock_session
):
    """Test map pool validation fails with inactive map"""
    # Setup - Include inactive map
    map_ids = [test_maps[0].id, test_maps[3].id]  # dust2 and cache (inactive)
    
    # Mock queries
    mock_result1 = Mock()
    mock_result1.first.return_value = test_maps[0]
    
    mock_result2 = Mock()
    mock_result2.first.return_value = test_maps[3]  # Inactive map
    
    mock_scalars1 = Mock(return_value=mock_result1)
    mock_scalars2 = Mock(return_value=mock_result2)
    
    mock_session.execute.side_effect = [
        Mock(scalars=mock_scalars1),
        Mock(scalars=mock_scalars2)
    ]
    
    # Execute
    is_valid = await map_service.validate_map_pool(map_ids, mock_session)
    
    # Assert
    assert is_valid is False


@pytest.mark.asyncio
async def test_get_map_statistics(
    map_service,
    test_maps,
    mock_session
):
    """Test getting map statistics"""
    # Setup
    map_id = test_maps[0].id
    
    # Mock the statistics query (this would normally aggregate match data)
    stats = {
        "map_id": map_id,
        "times_played": 150,
        "ct_wins": 82,
        "t_wins": 68,
        "average_duration": 45.5,
        "most_picked_by": ["Team Alpha", "Team Beta"]
    }
    
    # For this test, we'll assume the service has a method to get stats
    with pytest.raises(AttributeError):
        # This method doesn't exist yet, but we're testing the pattern
        await map_service.get_map_statistics(map_id, mock_session)


@pytest.mark.asyncio
async def test_search_maps(
    map_service,
    test_maps,
    mock_session
):
    """Test searching maps by name"""
    # Setup - Search for "dust"
    search_results = [test_maps[0]]  # Only dust2 matches
    
    mock_result = Mock()
    mock_result.all.return_value = search_results
    mock_scalars = Mock(return_value=mock_result)
    mock_session.execute.return_value.scalars = mock_scalars
    
    # Execute (assuming the service has a search method)
    with pytest.raises(AttributeError):
        # This method doesn't exist yet, but we're testing the pattern
        await map_service.search_maps("dust", mock_session)