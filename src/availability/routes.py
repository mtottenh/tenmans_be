# availability/routes.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import uuid

from auth.dependencies import get_current_player, require_team_captain
from auth.models import Player
from db.main import get_session
from competitions.models.scheduling import (
    PlayerAvailability,
    TeamAvailability,
    ScheduleSuggestion,
    AvailabilityType,
    AvailabilityStatus
)
from .schemas import (
    AvailabilityCreate,
    AvailabilityResponse,
    TeamAvailabilityResponse,
    ScheduleSuggestionResponse
)
from services.availability import availability_service

availability_router = APIRouter(prefix="/availability")

@availability_router.post("/", response_model=AvailabilityResponse)
async def add_availability(
    availability_data: AvailabilityCreate,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Add availability for the current player"""
    
    try:
        availability = await availability_service.add_availability(
            player=current_player,
            availability_data=availability_data.dict(),
            actor=current_player,
            session=session
        )
        return availability
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@availability_router.get("/me", response_model=List[AvailabilityResponse])
async def get_my_availability(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    tournament_id: Optional[uuid.UUID] = None,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Get personal availability"""
    
    return await availability_service.get_player_availability(
        player=current_player,
        start_date=start_date,
        end_date=end_date,
        tournament_id=tournament_id,
        session=session
    )

@availability_router.patch("/{availability_id}", response_model=AvailabilityResponse)
async def update_availability(
    availability_id: uuid.UUID,
    availability_update: Dict,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Update availability"""
    
    availability = await session.get(PlayerAvailability, availability_id)
    if not availability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Availability not found"
        )
    
    if availability.player_id != current_player.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only update your own availability"
        )
    
    # Update fields
    for key, value in availability_update.items():
        if hasattr(availability, key):
            setattr(availability, key, value)
    
    session.add(availability)
    await session.commit()
    return availability

@availability_router.delete("/{availability_id}")
async def delete_availability(
    availability_id: uuid.UUID,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Cancel availability"""
    
    availability = await session.get(PlayerAvailability, availability_id)
    if not availability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Availability not found"
        )
    
    if availability.player_id != current_player.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only cancel your own availability"
        )
    
    await availability_service.update_availability_status(
        availability=availability,
        new_status=AvailabilityStatus.CANCELLED,
        actor=current_player,
        session=session,
        reason="User cancelled availability"
    )
    
    return {"status": "cancelled"}

@availability_router.get(
    "/team/{team_id}",
    response_model=TeamAvailabilityResponse,
    dependencies=[Depends(require_team_captain)]
)
async def get_team_availability(
    team_id: uuid.UUID,
    date: datetime,
    tournament_id: uuid.UUID,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Get team availability overview"""
    
    return await availability_service.get_team_availability(
        team_id=team_id,
        date=date.date(),
        tournament_id=tournament_id,
        session=session
    )

@availability_router.get(
    "/team/{team_id}/optimal",
    response_model=List[ScheduleSuggestionResponse],
    dependencies=[Depends(require_team_captain)]
)
async def get_optimal_times(
    team_id: uuid.UUID,
    opponent_team_id: uuid.UUID,
    tournament_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Get optimal scheduling times"""
    
    suggestions = await availability_service.find_optimal_times(
        team_1_id=team_id,
        team_2_id=opponent_team_id,
        tournament_id=tournament_id,
        start_date=start_date,
        end_date=end_date,
        session=session
    )
    
    return suggestions