from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import uuid

from .schemas import JoinRequestStatus

from .models import TeamJoinRequest
from teams.models import Team
from auth.models import Player
from competitions.models.seasons import Season
from audit.service import AuditService
from teams.service import RosterService

class JoinRequestError(Exception):
    """Base exception for join request operations"""
    pass

class TeamJoinRequestService:
    def __init__(self):
        self.audit_service = AuditService()
        self.roster_service = RosterService()

    def _join_request_audit_details(self, request: TeamJoinRequest, action: str) -> Dict:
        """Extract audit details from a join request operation"""
        return {
            "action": action,
            "request_id": str(request.id),
            "team_id": str(request.team_id),
            "player_id": str(request.player_uid),
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
            player_uid=player.uid,
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
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Approve a join request"""
        if request.status != JoinRequestStatus.PENDING:
            raise JoinRequestError("Can only approve pending requests")

        # Update request status
        request.status = JoinRequestStatus.APPROVED
        request.responded_by = captain.uid
        request.responded_at = datetime.now()
        request.response_message = response_message
        request.updated_at = datetime.now()

        # Add player to roster
        await self.roster_service.add_player_to_roster(
            team=await session.get(Team, request.team_id),
            player=await session.get(Player, request.player_uid),
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
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Reject a join request"""
        if request.status != JoinRequestStatus.PENDING:
            raise JoinRequestError("Can only reject pending requests")

        request.status = JoinRequestStatus.REJECTED
        request.responded_by = captain.uid
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
        session: AsyncSession
    ) -> TeamJoinRequest:
        """Cancel a join request (by the requesting player)"""
        if request.player_uid != player.uid:
            raise JoinRequestError("Only requesting player can cancel request")

        if request.status != JoinRequestStatus.PENDING:
            raise JoinRequestError("Can only cancel pending requests")

        request.status = JoinRequestStatus.CANCELLED
        request.updated_at = datetime.now()

        session.add(request)
        return request

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
        result = await session.execute(stmt)
        return result.all()

    async def get_player_requests(
        self,
        player: Player,
        session: AsyncSession,
        include_resolved: bool = False
    ) -> List[TeamJoinRequest]:
        """Get all join requests made by a player"""
        stmt = select(TeamJoinRequest).where(TeamJoinRequest.player_uid == player.uid)
        if not include_resolved:
            stmt = stmt.where(TeamJoinRequest.status == JoinRequestStatus.PENDING)
        result = await session.execute(stmt)
        return result.all()

    async def _get_active_request(
        self,
        player: Player,
        season: Season,
        session: AsyncSession
    ) -> Optional[TeamJoinRequest]:
        """Check for existing active join request"""
        stmt = select(TeamJoinRequest).where(
            TeamJoinRequest.player_uid == player.uid,
            TeamJoinRequest.season_id == season.id,
            TeamJoinRequest.status == JoinRequestStatus.PENDING
        )
        result = await session.execute(stmt)
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
        expired_requests = (await session.execute(stmt)).all()
        
        for request in expired_requests:
            request.status = JoinRequestStatus.EXPIRED
            request.updated_at = datetime.now()
            session.add(request)
            
        await session.commit()
        return len(expired_requests)