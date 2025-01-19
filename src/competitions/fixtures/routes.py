from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
import uuid
from datetime import datetime, timedelta

from competitions.models.tournaments import Tournament
from competitions.models.rounds import Round
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.seasons import Season
from competitions.fixtures.schemas import (
    FixtureCreate,
    FixtureUpdate,
    FixturePage,
    FixtureDetailed,
    FixtureReschedule,
    FixtureForfeit,
    MatchPlayerCreate,
    UpcomingFixturesResponse
)
from competitions.fixtures.service import FixtureServiceError
from services.fixture import fixture_service
from db.main import get_session
from auth.models import Player
from auth.dependencies import (
    get_current_player,
    require_fixture_admin,
    require_tournament_admin,
    require_team_captain,
)
from competitions.season.dependencies import get_active_season

fixture_router = APIRouter(prefix="/fixtures")


@fixture_router.get(
    "/",
    response_model=FixturePage,
    dependencies=[Depends(require_fixture_admin)]
)
async def get_all_fixtures(
    tournament_id: Optional[uuid.UUID] = None,
    status: Optional[List[FixtureStatus]] = None,
    page: int = 1,
    size: int = 20,
    session: AsyncSession = Depends(get_session)
):
    """Get all fixtures with pagination and optional filters"""
    fixtures, total = await fixture_service.get_fixtures(
        tournament_id=tournament_id,
        status=status,
        offset=(page - 1) * size,
        limit=size,
        session=session
    )
    
    return FixturePage(
        items=fixtures,
        total=total,
        page=page,
        size=size,
        has_next=total > page * size,
        has_previous=page > 1
    )

@fixture_router.get("/upcoming", response_model=UpcomingFixturesResponse)
async def get_upcoming_fixtures(
    days: int = 7,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player),
    current_season: Season = Depends(get_active_season)
):
    """Get upcoming fixtures for the current season"""
    if not current_season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active season found"
        )
    
    fixtures = await fixture_service.get_upcoming_fixtures(
        season_id=current_season.id,
        days=days,
        session=session
    )
    
    # Count fixtures in different time periods
    now = datetime.now()
    next_24h = sum(1 for f in fixtures 
                   if f.scheduled_at <= now + timedelta(days=1))
    next_week = sum(1 for f in fixtures 
                    if f.scheduled_at <= now + timedelta(days=7))
    
    return UpcomingFixturesResponse(
        items=fixtures,
        total=len(fixtures),
        next_24h=next_24h,
        next_week=next_week
    )

@fixture_router.get(
    "/{fixture_id}",
    response_model=FixtureDetailed
)
async def get_fixture(
    fixture_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Get detailed fixture information"""
    fixture = await fixture_service.get_fixture_with_details(fixture_id, session)
    if not fixture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fixture not found"
        )
    return fixture

@fixture_router.post(
    "/",
    response_model=FixtureDetailed,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tournament_admin)]
)
async def create_fixture(
    fixture_data: FixtureCreate,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Create a new fixture"""
    try:
        return await fixture_service.create_fixture(
            fixture_data=fixture_data,
            actor=current_player,
            session=session
        )
    except FixtureServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@fixture_router.patch(
    "/{fixture_id}/reschedule",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_tournament_admin)]
)
async def reschedule_fixture(
    fixture_id: uuid.UUID,
    reschedule_data: FixtureReschedule,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Reschedule a fixture"""
    try:
        fixture = await fixture_service.get_fixture(fixture_id, session)
        if not fixture:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fixture not found"
            )
            
        return await fixture_service.reschedule_fixture(
            fixture=fixture,
            reschedule_data=reschedule_data,
            actor=current_player,
            session=session
        )
    except FixtureServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@fixture_router.post(
    "/{fixture_id}/start",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_tournament_admin)]
)
async def start_fixture(
    fixture_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Start a fixture"""
    try:
        fixture = await fixture_service.get_fixture(fixture_id, session)
        if not fixture:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fixture not found"
            )
            
        return await fixture_service.start_fixture(
            fixture=fixture,
            actor=current_player,
            session=session
        )
    except FixtureServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@fixture_router.post(
    "/{fixture_id}/forfeit",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_tournament_admin)]
)
async def forfeit_fixture(
    fixture_id: uuid.UUID,
    forfeit_data: FixtureForfeit,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Mark a fixture as forfeited"""
    try:
        fixture = await fixture_service.get_fixture(fixture_id, session)
        if not fixture:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fixture not found"
            )
            
        return await fixture_service.forfeit_fixture(
            fixture=fixture,
            forfeit_data=forfeit_data,
            actor=current_player,
            session=session
        )
    except FixtureServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@fixture_router.post(
    "/{fixture_id}/complete",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_tournament_admin)]
)
async def complete_fixture(
    fixture_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Complete a fixture"""
    try:
        fixture = await fixture_service.get_fixture(fixture_id, session)
        if not fixture:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fixture not found"
            )
            
        return await fixture_service.complete_fixture(
            fixture=fixture,
            actor=current_player,
            session=session
        )
    except FixtureServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@fixture_router.post(
    "/{fixture_id}/players",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_team_captain)]
)
async def add_match_player(
    fixture_id: uuid.UUID,
    player_data: MatchPlayerCreate,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Add a player to a match"""
    try:
        return await fixture_service.add_match_player(
            fixture_id=fixture_id,
            player_data=player_data,
            actor=current_player,
            session=session
        )
    except FixtureServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@fixture_router.delete(
    "/{fixture_id}/players/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_team_captain)]
)
async def remove_match_player(
    fixture_id: uuid.UUID,
    player_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_player: Player = Depends(get_current_player)
):
    """Remove a player from a match"""
    try:
        await fixture_service.remove_match_player(
            fixture_id=fixture_id,
            player_id=player_id,
            actor=current_player,
            session=session
        )
    except FixtureServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )