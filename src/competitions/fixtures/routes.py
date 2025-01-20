from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
import uuid
from datetime import datetime, timedelta

from competitions.models.fixtures import FixtureStatus
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
from services.tournament import tournament_service
from db.main import get_session
from auth.models import Player
from auth.dependencies import (
    get_current_player,
    require_view_matches,
    require_tournament_manage,
    require_team_captain,
    require_schedule_matches,
    require_confirm_results,
)
from competitions.season.dependencies import get_active_season

fixture_router = APIRouter(prefix="/id/{tournament_id}/fixtures")


global_fixture_router = APIRouter(prefix="/fixtures")
@global_fixture_router.get("/upcoming", response_model=UpcomingFixturesResponse)
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
    "/",
    response_model=FixturePage,
    dependencies=[Depends(require_view_matches)]
)
async def get_all_fixtures(
    tournament_id: uuid.UUID,
    # status: Optional[List[FixtureStatus]] = None,
    # page: int = 1,
    # size: int = 20,
    session: AsyncSession = Depends(get_session)
):
    """Get all fixtures with pagination and optional filters"""
    try:
        tournament = await tournament_service.get_tournament(tournament_id, session)
        if tournament is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No tournament with id {tournament_id}"
            )
        
        return await fixture_service.get_tournament_fixtures(tournament.id, session)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{str(e)}"
        )
    
    # fixtures, total = await fixture_service.get_tournament_fixtures(
    #     tournament_id=tournament_id,
    #     status=status,
    #     # offset=(page - 1) * size,
    #     # limit=size,
    #     session=session
    # )
    
    # return FixturePage(
    #     items=fixtures,
    #     total=total,
    #     page=page,
    #     size=size,
    #     has_next=total > page * size,
    #     has_previous=page > 1
    # )


@fixture_router.get(
    "/id/{fixture_id}",
    response_model=FixtureDetailed
)
async def get_fixture(
    tournament_id: uuid.UUID,
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
    dependencies=[Depends(require_tournament_manage)]
)
async def create_fixture(
    tournament_id: uuid.UUID,
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
    "/id/{fixture_id}/reschedule",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_schedule_matches)]
)
async def reschedule_fixture(
    tournament_id: uuid.UUID,
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
    "/id/{fixture_id}/start",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_schedule_matches)]
)
async def start_fixture(
    tournament_id: uuid.UUID,
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
    "/id/{fixture_id}/forfeit",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_tournament_manage)]
)
async def forfeit_fixture(
    tournament_id: uuid.UUID,
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
    "/id/{fixture_id}/complete",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_confirm_results)]
)
async def complete_fixture(
    tournament_id: uuid.UUID,
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
    "/id/{fixture_id}/team/id/{team_id}/players",
    response_model=FixtureDetailed,
    dependencies=[Depends(require_team_captain)]
)
async def add_match_player(
    tournament_id: uuid.UUID,
    fixture_id: uuid.UUID,
    team_id: uuid.UUID,
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
    "/id/{fixture_id}/team/id/{team_id}/players/id/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_team_captain)]
)
async def remove_match_player(
    tournament_id: uuid.UUID,
    fixture_id: uuid.UUID,
    team_id: uuid.UUID,
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