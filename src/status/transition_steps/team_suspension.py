from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player, Role
from auth.schemas import ScopeType
from status.pipeline import TransitionStep
from teams.base_schemas import TeamStatus, TeamCaptainStatus
from teams.models import Team, TeamCaptain

LOG = logging.getLogger('uvicorn.error')

class TeamCaptainTemporaryStep(TransitionStep):
    """Pipeline step to update captain roles when a team is suspended"""
    
    async def execute(
        self,
        entity: Team,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != TeamStatus.SUSPENDED.value:
            return  # Only act on suspend transitions
        
        # Get all active captains
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == entity.id,
            TeamCaptain.status == TeamCaptainStatus.ACTIVE
        )
        result = await session.execute(stmt)
        captains = result.scalars().all()
        
        # Update captain status to TEMPORARY
        # Note: This doesn't remove roles, just marks status as temporary
        for captain in captains:
            LOG.info(f"Setting captain {captain.player_id} to TEMPORARY due to team suspension")
            captain.status = TeamCaptainStatus.TEMPORARY
            session.add(captain)


class TeamFixtureRescheduleStep(TransitionStep):
    """Pipeline step to reschedule upcoming fixtures when a team is suspended"""
    
    async def execute(
        self,
        entity: Team,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != TeamStatus.SUSPENDED.value:
            return  # Only act on suspend transitions
        
        from competitions.models.fixtures import Fixture, FixtureStatus
        
        # Get all scheduled fixtures happening within the next 14 days
        now = datetime.utcnow()
        two_weeks_later = now + timedelta(days=14)
        
        stmt = select(Fixture).where(
            (Fixture.team_1 == entity.id) | (Fixture.team_2 == entity.id),
            Fixture.status == FixtureStatus.SCHEDULED,
            Fixture.scheduled_at >= now,
            Fixture.scheduled_at <= two_weeks_later
        )
        result = await session.execute(stmt)
        fixtures = result.scalars().all()
        
        # Reschedule each fixture to two weeks from now
        for fixture in fixtures:
            LOG.info(f"Rescheduling fixture {fixture.id} due to team suspension")
            fixture.rescheduled_from = fixture.scheduled_at
            fixture.scheduled_at = two_weeks_later
            fixture.rescheduled_by = actor.id
            fixture.reschedule_reason = f"Team {entity.name} suspended: {context.get('reason')}"
            fixture.updated_at = datetime.now()
            
            session.add(fixture)


class TeamCaptainReactivateStep(TransitionStep):
    """Pipeline step to reactivate captain roles when a team is reactivated"""
    
    async def execute(
        self,
        entity: Team,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context
    ) -> None:
        if new_status != TeamStatus.ACTIVE.value or old_status != TeamStatus.SUSPENDED.value:
            return  # Only act on reactivation from suspended transitions
        
        # Get all temporary captains
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == entity.id,
            TeamCaptain.status == TeamCaptainStatus.TEMPORARY
        )
        result = await session.execute(stmt)
        captains = result.scalars().all()
        
        # Restore captain status to ACTIVE
        for captain in captains:
            LOG.info(f"Restoring captain {captain.player_id} to ACTIVE due to team reactivation")
            captain.status = TeamCaptainStatus.ACTIVE
            session.add(captain)