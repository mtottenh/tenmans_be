from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import uuid
from sqlalchemy.orm import joinedload, selectinload

from audit.models import AuditEventType
from auth.service.permission import PermissionService, create_permission_service
from competitions.season.service import SeasonService, create_season_service
from status.manager.join_request import initialize_join_request_manager
from status.service import StatusTransitionService, create_status_transition_service
from teams.service.captain import CaptainService, create_captain_service

from .schemas import JoinRequestStatus

from .models import TeamJoinRequest
from teams.models import Team
from auth.models import Player, Role
from competitions.models.seasons import Season
from audit.service import AuditService, create_audit_service
from teams.service.roster import RosterService, create_roster_service
from teams.service.team import TeamService, create_team_service

class JoinRequestError(Exception):
    """Base exception for join request operations"""
    pass

class TeamJoinRequestService:
    def __init__(
        self,
        roster_service: RosterService,
        team_service: TeamService,
        status_transition_service: Optional[StatusTransitionService] = None
    ):
        self.roster_service = roster_service
        self.team_service = team_service
        self.status_transition_service = status_transition_service or create_status_transition_service()
        
        # Register join request status manager
        join_request_manager = initialize_join_request_manager()
        self.status_transition_service.register_transition_manager("TeamJoinRequest", join_request_manager)


    def _join_request_audit_details(self, request: TeamJoinRequest,  context: Dict) -> Dict:
        """Extract audit details from a join request operation"""
        return {
            "request_id": str(request.id),
            "team_id": str(request.team_id),
            "player_id": str(request.player_id),
            "season_id": str(request.season_id),
            "status": request.status,
            "timestamp": datetime.now().isoformat(),
            "message": request.message
        }

    async def change_request_status(
        self,
        request: TeamJoinRequest,
        new_status: JoinRequestStatus,
        reason: str,
        actor: Player,
        session: AsyncSession,
        entity_metadata: Optional[Dict] = None
    ) -> TeamJoinRequest:
        """Change a join request's status with validation"""
        return await self.status_transition_service.transition_status(
            entity=request,
            new_status=new_status,
            reason=reason,
            actor=actor,
            entity_metadata=entity_metadata,
            session=session
        )

    async def create_request(
        self,
        player: Player,
        team: Team,
        season: Season,
        message: Optional[str],
        actor: Player,
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Create a new join request"""
        request = TeamJoinRequest(
            player_id=player.id,
            team_id=team.id,
            season_id=season.id,
            message=message,
            created_at=datetime.now()
        )
        session.add(request)
        await session.flush()
        
        # Use status transition service to set initial status
        await self.change_request_status(
            request=request,
            new_status=JoinRequestStatus.PENDING,
            reason="Initial join request",
            actor=actor,
            session=session
        )
        
        return request

    async def approve_request(
        self,
        request: TeamJoinRequest,
        captain: Player,
        response_message: Optional[str],
        actor: Player,
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Approve a join request"""
        await self.change_request_status(
            request=request,
            new_status=JoinRequestStatus.APPROVED,
            reason=response_message or "Request approved",
            actor=actor,
            entity_metadata={"response_message": response_message},
            session=session
        )
        
        # Add player to team roster
        await self.roster_service.add_player_to_roster(
            team=request.team,
            player=request.player,
            season=request.season,
            actor=actor,
            session=session
        )
        
        return request

    async def reject_request(
        self,
        request: TeamJoinRequest,
        captain: Player,
        response_message: Optional[str],
        actor: Player,
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Reject a join request"""
        return await self.change_request_status(
            request=request,
            new_status=JoinRequestStatus.REJECTED,
            reason=response_message or "Request rejected",
            actor=actor,
            entity_metadata={"response_message": response_message},
            session=session
        )

    async def cancel_request(
        self,
        request: TeamJoinRequest,
        player: Player,
        actor: Player,
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Cancel a join request"""
        return await self.change_request_status(
            request=request,
            new_status=JoinRequestStatus.CANCELLED,
            reason="Request cancelled by player",
            actor=actor,
            session=session
        )

        
    async def get_request_by_id(
        self,
        request_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[TeamJoinRequest]:
        """Get a join request by ID"""
        stmt = select(TeamJoinRequest).where(TeamJoinRequest.id == request_id)
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_team_req_with_req_id(
        self,
        team_id: uuid.UUID,
        request_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[TeamJoinRequest]:
        """Get a specific join request for a team"""
        stmt = select(TeamJoinRequest).where(
            TeamJoinRequest.team_id == team_id,
            TeamJoinRequest.id == request_id
        )
        result = (await session.execute(stmt)).scalars()
        return result.first()
        
    async def get_pending_team_request_by_id(
        self,
        team_id: uuid.UUID,
        request_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[TeamJoinRequest]:
        """Get a pending join request by ID"""
        stmt = select(TeamJoinRequest).where(
            TeamJoinRequest.team_id == team_id,
            TeamJoinRequest.id == request_id,
            TeamJoinRequest.status == JoinRequestStatus.PENDING
        )
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_team_requests(
        self,
        team: Team,
        session: AsyncSession,
        include_resolved: bool = False
    ) -> List[TeamJoinRequest]:
        """Get all join requests for a team"""
        stmt = select(TeamJoinRequest).where(TeamJoinRequest.team_id == team.id)
        if not include_resolved:
            stmt = stmt.where(TeamJoinRequest.status == JoinRequestStatus.PENDING)
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_player_requests(
        self,
        player: Player,
        session: AsyncSession,
        include_resolved: bool = False
    ) -> List[TeamJoinRequest]:
        """Get all join requests made by a player"""
        stmt = select(TeamJoinRequest).where(TeamJoinRequest.player_id == player.id)
        if not include_resolved:
            stmt = stmt.where(TeamJoinRequest.status == JoinRequestStatus.PENDING)
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def cleanup_expired_requests(
        self,
        session: AsyncSession,
        expiry_days: int = 7
    ) -> int:
        """Mark old pending requests as expired"""
        expiry_date = datetime.now() - timedelta(days=expiry_days)
        stmt = select(TeamJoinRequest).where(
            TeamJoinRequest.status == JoinRequestStatus.PENDING,
            TeamJoinRequest.created_at < expiry_date
        )
        expired_requests = (await session.execute(stmt)).scalars().all()
        
        for request in expired_requests:
            await self.change_request_status(
                request=request,
                new_status=JoinRequestStatus.EXPIRED,
                reason=f"Request expired after {expiry_days} days",
                actor=None,  # System action
                session=session
            )
            
        return len(expired_requests)




def create_team_join_request_service(
    roster_service: Optional[RosterService] = None,
    team_service: Optional[TeamService] = None,
    audit_service: Optional[AuditService] = None,
    permission_service: Optional[PermissionService] = None,
    status_transition_service: Optional[StatusTransitionService] = None,
    captain_service: Optional[CaptainService] = None,
    season_service: Optional[SeasonService] = None
) -> TeamJoinRequestService:
    audit_service = audit_service or create_audit_service()
    permission_service = permission_service or create_permission_service(audit_service)
    season_service = season_service or create_season_service()
    status_transition_service = status_transition_service or create_status_transition_service(audit_service, permission_service)
    captain_service = captain_service or create_captain_service(audit_service, permission_service, status_transition_service)
    roster_service = roster_service or create_roster_service(audit_service, season_service, permission_service, status_transition_service)
    team_service = team_service or create_team_service(audit_service, roster_service, season_service, captain_service, permission_service, status_transition_service)
    return TeamJoinRequestService(roster_service, team_service, status_transition_service)