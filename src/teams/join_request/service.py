from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import uuid
from sqlalchemy.orm import joinedload, selectinload

from competitions.season.service import SeasonService, create_season_service

from .schemas import JoinRequestStatus

from .models import TeamJoinRequest
from teams.models import Team
from auth.models import Player, Role
from competitions.models.seasons import Season
from audit.service import AuditService
from teams.service.roster import RosterService, create_roster_service
from teams.service.team import TeamService, create_team_service

class JoinRequestError(Exception):
    """Base exception for join request operations"""
    pass

class TeamJoinRequestService:
    def __init__(self, roster_service: Optional[RosterService] = None,
                 team_service: Optional[TeamService] = None,
                 ):
        self.roster_service = roster_service or create_roster_service()
        self.team_service = team_service or create_team_service(roster_service.audit_service, roster_service, None)

    def _join_request_audit_details(self, request: TeamJoinRequest) -> Dict:
        """Extract audit details from a join request operation"""
        return {
            "request_id": str(request.id),
            "team_id": str(request.team_id),
            "player_id": str(request.player_id),
            "season_id": str(request.season_id),
            "status": request.status,
            "timestamp": datetime.now().isoformat(),
        }

    @AuditService.audited_transaction(
        action_type="join_request_create",
        entity_type="join_request",
        details_extractor=_join_request_audit_details
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
        # Check if player already has an active request
        existing_request = await self._get_active_request(player, season, session)
        if existing_request:
            raise JoinRequestError("Player already has an active join request")

        # Check if player is already on a team
        current_roster = await self.roster_service._get_player_roster(player, season, session)
        if current_roster:
            raise JoinRequestError("Player is already on a team this season")

        # Create request
        request = TeamJoinRequest(
            player_id=player.id,
            team_id=team.id,
            season_id=season.id,
            message=message
        )
        
        session.add(request)
        return request

    @AuditService.audited_transaction(
        action_type="join_request_approve",
        entity_type="join_request",
        details_extractor=_join_request_audit_details
    )
    async def approve_request(
        self,
        request: TeamJoinRequest,
        captain: Player,
        response_message: Optional[str],
        actor: Player,
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Approve a join request"""
        if request.status != JoinRequestStatus.PENDING:
            raise JoinRequestError("Can only approve pending requests")
        if not await self.team_service.player_is_team_captain(captain, request.team, session):
            raise JoinRequestError("Only team captains can review requests")
        # Update request status
        request.status = JoinRequestStatus.APPROVED
        request.responded_by = captain.id
        request.responded_at = datetime.now()
        request.response_message = response_message
        request.updated_at = datetime.now()

        # Add player to roster
        await self.roster_service.add_player_to_roster(
            team=await session.get(Team, request.team_id),
            player=await session.get(Player, request.player_id),
            season=await session.get(Season, request.season_id),
            actor=captain,
            session=session
        )

        session.add(request)
        return request

    @AuditService.audited_transaction(
        action_type="join_request_reject",
        entity_type="join_request",
        details_extractor=_join_request_audit_details
    )
    async def reject_request(
        self,
        request: TeamJoinRequest,
        captain: Player,
        response_message: Optional[str],
        actor: Player,
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Reject a join request"""
        if request.status != JoinRequestStatus.PENDING:
            raise JoinRequestError("Can only reject pending requests")

        request.status = JoinRequestStatus.REJECTED
        request.responded_by = captain.id
        request.responded_at = datetime.now()
        request.response_message = response_message
        request.updated_at = datetime.now()

        session.add(request)
        return request

    @AuditService.audited_transaction(
        action_type="join_request_cancel",
        entity_type="join_request",
        details_extractor=_join_request_audit_details
    )
    async def cancel_request(
        self,
        request: TeamJoinRequest,
        player: Player,
        actor: Player,
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Cancel a join request (by the requesting player)"""
        if request.player_id != player.id:
            raise JoinRequestError("Only requesting player can cancel request")

        if request.status != JoinRequestStatus.PENDING:
            raise JoinRequestError("Can only cancel pending requests")

        request.status = JoinRequestStatus.CANCELLED
        request.updated_at = datetime.now()

        session.add(request)
        return request
    async def get_request_by_id(self, req_id: str, session: AsyncSession) -> TeamJoinRequest:
        stmt = select(TeamJoinRequest).where(TeamJoinRequest.id == req_id).options(
            selectinload(TeamJoinRequest.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions),
            selectinload(TeamJoinRequest.team),
            selectinload(TeamJoinRequest.responder)
            .selectinload(Player.roles)
            .selectinload(Role.permissions)
        )
        result = (await session.execute(stmt)).scalars()
        return result.first()
    
    async def get_pending_team_request_by_id(self, team_id: str, req_id: str, session: AsyncSession) -> TeamJoinRequest:
        stmt = select(TeamJoinRequest).where(TeamJoinRequest.id == req_id, TeamJoinRequest.team_id == team_id, TeamJoinRequest.status == JoinRequestStatus.PENDING).options(
            selectinload(TeamJoinRequest.player)
            .selectinload(Player.roles)
            .selectinload(Role.permissions),
            selectinload(TeamJoinRequest.team)
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
            stmt = stmt.where(TeamJoinRequest.status == JoinRequestStatus.PENDING).options(
                selectinload(TeamJoinRequest.team),
                selectinload(TeamJoinRequest.player)
                .selectinload(Player.roles)
                .selectinload(Role.permissions)
            )
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

    async def _get_active_request(
        self,
        player: Player,
        season: Season,
        session: AsyncSession
    ) -> Optional[TeamJoinRequest]:
        """Check for existing active join request"""
        stmt = select(TeamJoinRequest).where(
            TeamJoinRequest.player_id == player.id,
            TeamJoinRequest.season_id == season.id,
            TeamJoinRequest.status == JoinRequestStatus.PENDING
        )
        result = (await session.execute(stmt)).scalars()
        return result.first()

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
        expired_requests = ((await session.execute(stmt)).scalars()).all()
        
        for request in expired_requests:
            request.status = JoinRequestStatus.EXPIRED
            request.updated_at = datetime.now()
            session.add(request)
            
        await session.commit()
        return len(expired_requests)
    




def create_team_join_request_service(roster_svc: Optional[RosterService] = None,
                 team_svc: Optional[TeamService] = None,
                 ) -> TeamJoinRequestService:
    
    
    roster_service = roster_svc or create_roster_service()
    team_service = team_svc or create_team_service(roster_service.audit_service, roster_service, None)
    return TeamJoinRequestService(roster_service, team_service)