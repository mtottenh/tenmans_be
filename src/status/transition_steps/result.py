"""Pipeline steps for result status transitions"""

import logging
from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from auth.service.permission import PermissionService
from matches.models import ConfirmationStatus, MatchDispute, Result
from status.pipeline import TransitionStep

LOG = logging.getLogger("uvicorn.error")


class NotifyOpposingTeamStep(TransitionStep):
    """Notify the opposing team about result submission"""
    
    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: Result,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Send notification to opposing team"""
        if new_status != ConfirmationStatus.PENDING:
            return
            
        # Determine which team to notify
        fixture = entity.fixture
        submitting_team = None
        opposing_team = None
        
        # Find which team the actor belongs to
        if actor.id in [c.player_id for c in fixture.team_1_obj.captains]:
            submitting_team = fixture.team_1_obj
            opposing_team = fixture.team_2_obj
        else:
            submitting_team = fixture.team_2_obj
            opposing_team = fixture.team_1_obj
            
        # TODO: Send notification to opposing team captains
        LOG.info(f"Notifying team {opposing_team.name} about result submission for fixture {fixture.id}")


class CreateDisputeStep(TransitionStep):
    """Create a dispute record when result is disputed"""
    
    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: Result,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Create dispute record"""
        if new_status != ConfirmationStatus.DISPUTED:
            return
            
        # Create dispute
        dispute = MatchDispute(
            result_id=entity.id,
            disputed_by=actor.id,
            reason=reason or "Result disputed",
            evidence_urls=context.get("evidence_urls", []),
        )
        
        session.add(dispute)
        await session.flush()
        
        LOG.info(f"Created dispute {dispute.id} for result {entity.id}")


class UpdateFixtureStatusStep(TransitionStep):
    """Update fixture status based on result confirmation"""
    
    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: Result,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Update fixture status when all results are confirmed"""
        if new_status not in [ConfirmationStatus.CONFIRMED, ConfirmationStatus.ADMIN_OVERRIDE]:
            return
            
        fixture = entity.fixture
        
        # Check if all maps in the fixture are confirmed
        all_confirmed = True
        for result in fixture.results:
            if result.confirmation_status not in [
                ConfirmationStatus.CONFIRMED,
                ConfirmationStatus.ADMIN_OVERRIDE,
            ]:
                all_confirmed = False
                break
                
        if all_confirmed:
            # Update fixture status to completed
            from competitions.models.fixtures import FixtureStatus
            
            fixture.status = FixtureStatus.COMPLETED
            session.add(fixture)
            await session.flush()
            
            LOG.info(f"Fixture {fixture.id} marked as completed after all results confirmed")


class NotifyAdminsStep(TransitionStep):
    """Notify admins when a result is disputed"""
    
    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: Result,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Send notification to admins about disputes"""
        if new_status != ConfirmationStatus.DISPUTED:
            return
            
        # TODO: Send notification to tournament admins
        LOG.info(f"Notifying admins about dispute for result {entity.id}")


class RecalculateStandingsStep(TransitionStep):
    """Recalculate tournament standings after result changes"""
    
    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: Result,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Recalculate standings if result was overridden"""
        if new_status not in [ConfirmationStatus.ADMIN_OVERRIDE, ConfirmationStatus.VOIDED]:
            return
            
        # TODO: Trigger standings recalculation
        fixture = entity.fixture
        tournament = fixture.tournament
        
        LOG.info(f"Recalculating standings for tournament {tournament.id} after result override")