from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
import uuid

from db.main import get_session
from auth.dependencies import (
    get_current_player, 
    require_admin,
    GlobalPermissionChecker
)
from auth.models import Player
from teams.models import Team
from teams.service import TeamService
from teams.dependencies import CaptainCheckerByTeamName
from competitions.season.dependencies import get_active_season
from competitions.models.seasons import Season
from .models import TeamJoinRequest, JoinRequestStatus
from .schemas import (
    JoinRequestCreate,
    JoinRequestResponse,
    JoinRequestList,
    JoinRequestUpdate,
    JoinRequestDetailed,
    JoinRequestStats
)
from .service import TeamJoinRequestService, JoinRequestError

join_request_router = APIRouter(prefix="/teams/join-requests")
join_request_service = TeamJoinRequestService()
team_service = TeamService()

# Additional permissions
require_team_captain = CaptainCheckerByTeamName()
require_moderator = GlobalPermissionChecker(["moderator"])

@join_request_router.post(
    "/{team_name}",
    response_model=JoinRequestDetailed,
    status_code=status.HTTP_201_CREATED
)
async def create_join_request(
    team_name: str,
    request_data: JoinRequestCreate,
    current_player: Player = Depends(get_current_player),
    active_season: Season = Depends(get_active_season),
    session: AsyncSession = Depends(get_session)
):
    """Create a request to join a team"""
    team = await team_service.get_team_by_name(team_name, session)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{team_name}' not found"
        )

    try:
        join_request = await join_request_service.create_request(
            player=current_player,
            team=team,
            season=active_season,
            message=request_data.message,
            session=session
        )
        return join_request
    except JoinRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@join_request_router.get(
    "/team/{team_name}",
    response_model=JoinRequestList,
    dependencies=[Depends(require_team_captain)]
)
async def get_team_join_requests(
    team_name: str,
    include_resolved: bool = False,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Get all join requests for a team (requires team captain)"""
    team = await team_service.get_team_by_name(team_name, session)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{team_name}' not found"
        )

    requests = await join_request_service.get_team_requests(
        team=team,
        session=session,
        include_resolved=include_resolved
    )
    
    # Calculate stats
    pending_count = sum(1 for r in requests if r.status == JoinRequestStatus.PENDING)
    return JoinRequestList(
        total=len(requests),
        pending_count=pending_count,
        requests=requests
    )

@join_request_router.get(
    "/my-requests",
    response_model=JoinRequestList
)
async def get_my_join_requests(
    include_resolved: bool = False,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Get all join requests made by current player"""
    requests = await join_request_service.get_player_requests(
        player=current_player,
        session=session,
        include_resolved=include_resolved
    )
    
    pending_count = sum(1 for r in requests if r.status == JoinRequestStatus.PENDING)
    return JoinRequestList(
        total=len(requests),
        pending_count=pending_count,
        requests=requests
    )

@join_request_router.get(
    "/{request_id}",
    response_model=JoinRequestDetailed
)
async def get_join_request(
    request_id: uuid.UUID,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Get details of a specific join request"""
    request = await join_request_service.get_request(request_id, session)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Join request not found"
        )
    
    # Check permissions - allow if:
    # - Player is the requester
    # - Player is team captain
    # - Player is admin/moderator
    is_requester = request.player_uid == current_player.uid
    is_captain = await team_service.player_is_team_captain(
        current_player,
        request.team,
        session
    )
    has_permission = await require_moderator(current_player, session)
    
    if not (is_requester or is_captain or has_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this request"
        )
    
    return request

@join_request_router.patch(
    "/{request_id}/approve",
    response_model=JoinRequestDetailed,
    dependencies=[Depends(require_team_captain)]
)
async def approve_join_request(
    request_id: uuid.UUID,
    response: JoinRequestResponse,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Approve a join request (requires team captain)"""
    try:
        request = await join_request_service.approve_request(
            request_id=request_id,
            captain=current_player,
            response_message=response.response_message,
            session=session
        )
        return request
    except JoinRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@join_request_router.patch(
    "/{request_id}/reject",
    response_model=JoinRequestDetailed,
    dependencies=[Depends(require_team_captain)]
)
async def reject_join_request(
    request_id: uuid.UUID,
    response: JoinRequestResponse,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Reject a join request (requires team captain)"""
    try:
        request = await join_request_service.reject_request(
            request_id=request_id,
            captain=current_player,
            response_message=response.response_message,
            session=session
        )
        return request
    except JoinRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@join_request_router.patch(
    "/{request_id}/cancel",
    response_model=JoinRequestDetailed
)
async def cancel_join_request(
    request_id: uuid.UUID,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Cancel a join request (only allowed by requesting player)"""
    try:
        request = await join_request_service.cancel_request(
            request_id=request_id,
            player=current_player,
            session=session
        )
        return request
    except JoinRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@join_request_router.get(
    "/team/{team_name}/stats",
    response_model=JoinRequestStats,
    dependencies=[Depends(require_team_captain)]
)
async def get_team_request_stats(
    team_name: str,
    current_player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session)
):
    """Get statistics for team join requests (requires team captain)"""
    team = await team_service.get_team_by_name(team_name, session)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{team_name}' not found"
        )
    
    requests = await join_request_service.get_team_requests(
        team=team,
        session=session,
        include_resolved=True
    )
    
    # Calculate stats
    total = len(requests)
    stats = {status: sum(1 for r in requests if r.status == status)
             for status in JoinRequestStatus}
    
    # Calculate average response time for resolved requests
    response_times = [
        (r.responded_at - r.created_at).total_seconds() / 3600  # Convert to hours
        for r in requests
        if r.responded_at is not None
    ]
    avg_response_time = (
        sum(response_times) / len(response_times)
        if response_times else None
    )
    
    return JoinRequestStats(
        total_requests=total,
        pending_requests=stats[JoinRequestStatus.PENDING],
        approved_requests=stats[JoinRequestStatus.APPROVED],
        rejected_requests=stats[JoinRequestStatus.REJECTED],
        cancelled_requests=stats[JoinRequestStatus.CANCELLED],
        expired_requests=stats[JoinRequestStatus.EXPIRED],
        average_response_time=avg_response_time
    )

@join_request_router.post(
    "/cleanup",
    response_model=dict,
    dependencies=[Depends(require_admin)]
)
async def cleanup_expired_requests(
    expiry_days: int = 7,
    session: AsyncSession = Depends(get_session)
):
    """Cleanup expired join requests (admin only)"""
    expired_count = await join_request_service.cleanup_expired_requests(
        session=session,
        expiry_days=expiry_days
    )
    return {
        "message": f"Cleaned up {expired_count} expired requests",
        "expired_count": expired_count
    }