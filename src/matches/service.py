from typing import List, Optional, Dict, Tuple
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from datetime import datetime
import uuid

from audit.models import AuditEventType
from competitions.models.fixtures import Fixture, FixtureStatus
from matches.models import Result, MatchPlayer, ConfirmationStatus
from matches.schemas import (
    ResultCreate,
    ResultConfirm,
    ResultDispute,
    AdminResultOverride,
    MatchPlayerAdd
)
from teams.models import Team, TeamCaptain
from auth.models import Player
from audit.service import AuditService
from competitions.fixtures.service import FixtureService

class MatchServiceError(Exception):
    """Base exception for match service errors"""
    pass

class MatchService:
    def __init__(self, audit_service: Optional[AuditService] = None,
                 fixture_service: Optional[FixtureService] = None
                 
                 ):
        self.audit_service = audit_service or AuditService()
        self.fixture_service = fixture_service or FixtureService(audit_service, None)

    def _result_audit_details(self, result: Result) -> dict:
        """Extract audit details from a result operation"""
        return {
            "result_id": str(result.id),
            "fixture_id": str(result.fixture_id),
            "map_id": str(result.map_id),
            "map_number": result.map_number,
            "team_1_score": result.team_1_score,
            "team_2_score": result.team_2_score,
            "team_1_side_first": result.team_1_side_first,
            "confirmation_status": result.confirmation_status,
            "submitted_by": str(result.submitted_by),
            "confirmed_by": str(result.confirmed_by) if result.confirmed_by else None,
            "admin_override": result.admin_override,
            "created_at": result.created_at.isoformat() if result.created_at else None,
            "updated_at": result.updated_at.isoformat() if result.updated_at else None
        }

    async def _validate_team_captain(
        self,
        player: Player,
        team: Team,
        session: AsyncSession
    ) -> bool:
        """Validate that a player is captain of a team"""
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == team.id,
            TeamCaptain.player_id == player.id
        )
        result = (await session.execute(stmt)).scalars()
        return result.first() is not None

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type="Result",
        details_extractor=_result_audit_details
    )
    async def submit_result(
        self,
        fixture_id: uuid.UUID,
        result_data: ResultCreate,
        submitting_player: Player,
        session: AsyncSession
    ) -> Result:
        """Submit a match result"""
        # Get fixture and validate state
        fixture = await self.fixture_service.get_fixture(fixture_id, session)
        if not fixture:
            raise MatchServiceError("Fixture not found")

        if fixture.status != FixtureStatus.IN_PROGRESS:
            raise MatchServiceError("Can only submit results for matches in progress")

        # Validate player is captain of one of the teams
        team_1 = await session.get(Team, fixture.team_1)
        team_2 = await session.get(Team, fixture.team_2)
        is_team1_captain = await self._validate_team_captain(submitting_player, team_1, session)
        is_team2_captain = await self._validate_team_captain(submitting_player, team_2, session)

        if not (is_team1_captain or is_team2_captain):
            raise MatchServiceError("Only team captains can submit results")

        # Create result
        result = Result(
            fixture_id=fixture_id,
            map_id=result_data.map_id,
            map_number=result_data.map_number,
            team_1_score=result_data.team_1_score,
            team_2_score=result_data.team_2_score,
            team_1_side_first=result_data.team_1_side_first,
            submitted_by=submitting_player.id,
            confirmation_status=ConfirmationStatus.PENDING,
            demo_url=result_data.demo_url,
            screenshot_urls=result_data.screenshot_urls,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        session.add(result)
        return result

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Result",
        details_extractor=_result_audit_details
    )
    async def confirm_result(
        self,
        result_id: uuid.UUID,
        confirming_player: Player,
        session: AsyncSession
    ) -> Result:
        """Confirm a match result"""
        result = await session.get(Result, result_id)
        if not result:
            raise MatchServiceError("Result not found")

        if result.confirmation_status != ConfirmationStatus.PENDING:
            raise MatchServiceError("Result is not pending confirmation")

        fixture = await self.fixture_service.get_fixture(result.fixture_id, session)
        
        # Validate confirming player is captain of the other team
        submitting_team = fixture.team_1 if result.submitted_by == fixture.team_1 else fixture.team_2
        confirming_team = fixture.team_2 if submitting_team == fixture.team_1 else fixture.team_1
        is_captain = await self._validate_team_captain(confirming_player, confirming_team, session)

        if not is_captain:
            raise MatchServiceError("Only the opposing team captain can confirm results")

        result.confirmation_status = ConfirmationStatus.CONFIRMED
        result.confirmed_by = confirming_player.id
        result.updated_at = datetime.now()

        session.add(result)

        # Complete fixture if all maps are confirmed
        if await self._check_all_maps_confirmed(fixture.id, session):
            await self.fixture_service.complete_fixture(fixture, confirming_player, session)

        return result

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Result",
        details_extractor=_result_audit_details
    )
    async def dispute_result(
        self,
        result_id: uuid.UUID,
        dispute_data: ResultDispute,
        disputing_player: Player,
        session: AsyncSession
    ) -> Result:
        """Dispute a match result"""
        result = await session.get(Result, result_id)
        if not result:
            raise MatchServiceError("Result not found")

        if result.confirmation_status != ConfirmationStatus.PENDING:
            raise MatchServiceError("Result is not pending confirmation")

        fixture = await self.fixture_service.get_fixture(result.fixture_id, session)

        # Validate disputing player is captain of the other team
        submitting_team = fixture.team_1 if result.submitted_by == fixture.team_1 else fixture.team_2
        disputing_team = fixture.team_2 if submitting_team == fixture.team_1 else fixture.team_1
        is_captain = await self._validate_team_captain(disputing_player, disputing_team, session)

        if not is_captain:
            raise MatchServiceError("Only the opposing team captain can dispute results")

        result.confirmation_status = ConfirmationStatus.DISPUTED
        result.dispute_reason = dispute_data.reason
        result.dispute_evidence = dispute_data.evidence_urls
        result.updated_at = datetime.now()

        session.add(result)
        return result

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Result",
        details_extractor=_result_audit_details
    )
    async def admin_override_result(
        self,
        result_id: uuid.UUID,
        override_data: AdminResultOverride,
        admin: Player,
        session: AsyncSession
    ) -> Result:
        """Admin override of a match result"""
        result = await session.get(Result, result_id)
        if not result:
            raise MatchServiceError("Result not found")

        # TODO: Validate admin permissions

        result.team_1_score = override_data.team_1_score
        result.team_2_score = override_data.team_2_score
        result.admin_override = True
        result.admin_override_by = admin.id
        result.admin_override_reason = override_data.reason
        result.confirmation_status = ConfirmationStatus.CONFIRMED
        result.updated_at = datetime.now()

        session.add(result)

        # Complete fixture if all maps are confirmed
        fixture = await self.fixture_service.get_fixture(result.fixture_id, session)
        if await self._check_all_maps_confirmed(fixture.id, session):
            await self.fixture_service.complete_fixture(fixture, admin, session)

        return result

    async def _check_all_maps_confirmed(
        self,
        fixture_id: uuid.UUID,
        session: AsyncSession
    ) -> bool:
        """Check if all maps for a fixture are confirmed"""
        stmt = select(Result).where(
            Result.fixture_id == fixture_id
        )
        results = ((await session.execute(stmt)).scalars()).all()

        return all(r.confirmation_status == ConfirmationStatus.CONFIRMED for r in results)

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type="MatchPlayer"
    )
    async def add_match_player(
        self,
        fixture_id: uuid.UUID,
        player_data: MatchPlayerAdd,
        actor: Player,
        session: AsyncSession
    ) -> MatchPlayer:
        """Add a player to a match"""
        fixture = await self.fixture_service.get_fixture(fixture_id, session)
        if not fixture:
            raise MatchServiceError("Fixture not found")

        if fixture.status != FixtureStatus.SCHEDULED:
            raise MatchServiceError("Can only add players before match starts")

        # Validate team assignment
        if player_data.team_id not in [fixture.team_1, fixture.team_2]:
            raise MatchServiceError("Invalid team assignment")

        # TODO: Validate player is on team roster

        match_player = MatchPlayer(
            fixture_id=fixture_id,
            player_id=player_data.player_id,
            team_id=player_data.team_id,
            is_substitute=player_data.is_substitute,
            created_at=datetime.now()
        )

        session.add(match_player)
        return match_player

    async def get_match_players(
        self,
        fixture_id: uuid.UUID,
        session: AsyncSession
    ) -> List[MatchPlayer]:
        """Get all players in a match"""
        stmt = select(MatchPlayer).where(
            MatchPlayer.fixture_id == fixture_id
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_team_match_players(
        self,
        fixture_id: uuid.UUID,
        team_id: uuid.UUID,
        session: AsyncSession
    ) -> List[MatchPlayer]:
        """Get all players for a team in a match"""
        stmt = select(MatchPlayer).where(
            MatchPlayer.fixture_id == fixture_id,
            MatchPlayer.team_id == team_id
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_match_results(
        self,
        fixture_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Result]:
        """Get all results for a match"""
        stmt = select(Result).where(
            Result.fixture_id == fixture_id
        ).order_by(Result.map_number)
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_match_summary(
        self,
        fixture_id: uuid.UUID,
        session: AsyncSession
    ) -> Dict:
        """Get summary of match results"""
        results = await self.get_match_results(fixture_id, session)
        
        if not results:
            return None

        return {
            "total_maps": len(results),
            "team_1_maps": sum(1 for r in results if r.team_1_score > r.team_2_score),
            "team_2_maps": sum(1 for r in results if r.team_2_score > r.team_1_score),
            "team_1_rounds": sum(r.team_1_score for r in results),
            "team_2_rounds": sum(r.team_2_score for r in results),
            "maps_complete": all(r.confirmation_status == ConfirmationStatus.CONFIRMED 
                               for r in results),
            "has_disputes": any(r.confirmation_status == ConfirmationStatus.DISPUTED 
                              for r in results)
        }
    
def create_match_service(audit_svc: Optional[AuditService] = None, fixture_svc: Optional[FixtureService] = None) -> MatchService:
    audit_service = audit_svc or AuditService()
    fixture_service = fixture_svc or FixtureService(audit_service, None)
    return MatchService(audit_service, fixture_service)