"""Pipeline steps for dispute status transitions"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from matches.models import ConfirmationStatus, DisputeStatus, MatchDispute, Result
from status.pipeline import TransitionStep

LOG = logging.getLogger("uvicorn.error")


class AssignReviewerStep(TransitionStep):
    """Assign a reviewer when dispute moves to under review"""

    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: MatchDispute,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Assign the actor as the reviewer"""
        if new_status != DisputeStatus.UNDER_REVIEW:
            return

        entity.resolved_by = actor.id
        session.add(entity)
        await session.flush()

        LOG.info(f"Assigned {actor.name} as reviewer for dispute {entity.id}")


class UpdateResultStatusStep(TransitionStep):
    """Update the associated result status based on dispute resolution"""

    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: MatchDispute,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Update result status when dispute is resolved"""
        if new_status not in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            return

        result = await session.get(Result, entity.result_id)
        if not result:
            LOG.error(f"Result {entity.result_id} not found for dispute {entity.id}")
            return

        resolution_type = context.get("resolution_type")

        if new_status == DisputeStatus.RESOLVED:
            # Update result based on resolution type
            if resolution_type == "accept_result":
                result.confirmation_status = ConfirmationStatus.CONFIRMED
            elif resolution_type == "override_result":
                result.confirmation_status = ConfirmationStatus.ADMIN_OVERRIDE
                result.admin_override = True
                result.admin_override_by = actor.id
                result.admin_override_reason = reason
                # Update scores if provided
                new_team1_score = context.get("team_1_score")
                new_team2_score = context.get("team_2_score")
                if new_team1_score is not None:
                    result.team_1_score = new_team1_score
                if new_team2_score is not None:
                    result.team_2_score = new_team2_score
            elif resolution_type == "void_match":
                result.confirmation_status = ConfirmationStatus.VOIDED
                result.voided = True
                result.voided_reason = reason

        elif new_status == DisputeStatus.REJECTED:
            # If dispute is rejected, confirm the original result
            result.confirmation_status = ConfirmationStatus.CONFIRMED

        session.add(result)
        await session.flush()

        LOG.info(f"Updated result {result.id} status to {result.confirmation_status}")


class NotifyTeamsStep(TransitionStep):
    """Notify teams about dispute resolution"""

    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: MatchDispute,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Send notifications to affected teams"""
        if new_status not in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED, DisputeStatus.ESCALATED]:
            return

        result = await session.get(Result, entity.result_id)
        fixture = result.fixture

        # TODO: Send notifications to both teams
        notification_message = f"Dispute {entity.id} has been {new_status.lower()}"
        if reason:
            notification_message += f": {reason}"

        LOG.info(f"Notifying teams about dispute resolution: {notification_message}")


class RecordResolutionStep(TransitionStep):
    """Record dispute resolution details"""

    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: MatchDispute,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Record resolution details"""
        if new_status not in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            return

        entity.resolved = True
        entity.resolved_by = actor.id
        entity.resolution_notes = reason
        entity.resolved_at = datetime.now(timezone.utc)

        session.add(entity)
        await session.flush()

        LOG.info(f"Recorded resolution for dispute {entity.id}")


class EscalateToHigherAuthorityStep(TransitionStep):
    """Handle escalation to higher authority"""

    async def execute(
        self,
        old_status: str,
        new_status: str,
        entity: MatchDispute,
        actor: Player,
        session: AsyncSession,
        reason: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Handle dispute escalation"""
        if new_status != DisputeStatus.ESCALATED:
            return

        # TODO: Create escalation ticket or notify higher authority
        escalation_reason = reason or "Dispute requires higher level review"
        LOG.info(f"Escalating dispute {entity.id}: {escalation_reason}")

        # Update dispute with escalation info
        entity.resolution_notes = f"Escalated by {actor.name}: {escalation_reason}"
        session.add(entity)
        await session.flush()