from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player
from auth.schemas import ScopeType
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.tournaments import TournamentRegistration, RegistrationStatus
from competitions.season.service import SeasonService
from status.pipeline import TransitionStep
from teams.base_schemas import RosterStatus, TeamCaptainStatus, TeamStatus
from teams.models import Team, TeamCaptain, Roster

LOG = logging.getLogger('uvicorn.error')

class TeamFixtureForfeitStep(TransitionStep):
    """Pipeline step to forfeit all scheduled and in-progress fixtures for a disbanded team"""
    
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
        if new_status != TeamStatus.DISBANDED.value:
            return  # Only act on disband transitions
        
        # Get all fixtures where the team is participating
        stmt = select(Fixture).where(
            (Fixture.team_1 == entity.id) | (Fixture.team_2 == entity.id),
            Fixture.status.in_([FixtureStatus.SCHEDULED, FixtureStatus.IN_PROGRESS])
        )
        result = await session.execute(stmt)
        fixtures = result.scalars().all()
        
        forfeit_reason = f"Team {entity.name} disbanded: {context.get('reason')}"
        
        # Forfeit each fixture
        for fixture in fixtures:
            LOG.info(f"Forfeiting fixture {fixture.id} due to team disbandment")
            # Determine the winner (the other team)
            if fixture.team_1 == entity.id:
                fixture.forfeit_winner = fixture.team_2
            else:
                fixture.forfeit_winner = fixture.team_1
                
            fixture.status = FixtureStatus.FORFEITED
            fixture.forfeit_reason = forfeit_reason
            fixture.updated_at = datetime.now()
            
            session.add(fixture)


class TeamRosterDeactivateStep(TransitionStep):
    """Pipeline step to update all active roster entries when a team is disbanded"""
    
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
        if new_status != TeamStatus.DISBANDED.value:
            return  # Only act on disband transitions
        
        # Get all active roster entries
        stmt = select(Roster).where(
            Roster.team_id == entity.id,
            Roster.status == RosterStatus.ACTIVE
        )
        result = await session.execute(stmt)
        rosters = result.scalars().all()
        
        # Update roster status to PAST
        for roster in rosters:
            LOG.info(f"Setting roster entry {roster.player_id} to PAST due to team disbandment")
            roster.status = RosterStatus.PAST
            roster.updated_at = datetime.now()
            session.add(roster)


class TeamCaptainDeactivateStep(TransitionStep):
    """Pipeline step to update captain roles when a team is disbanded"""
    
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
        if new_status != TeamStatus.DISBANDED.value:
            return  # Only act on disband transitions
        
        # Get all active captains
        stmt = select(TeamCaptain).where(
            TeamCaptain.team_id == entity.id,
            TeamCaptain.status.in_([TeamCaptainStatus.ACTIVE, TeamCaptainStatus.TEMPORARY])
        )
        result = await session.execute(stmt)
        captains = result.scalars().all()
        
        # Update captain status to DISBANDED
        for captain in captains:
            LOG.info(f"Setting captain {captain.player_id} to DISBANDED due to team disbandment")
            captain.status = TeamCaptainStatus.DISBANDED
            session.add(captain)


class TeamTournamentRegistrationStep(TransitionStep):
    """Pipeline step to update tournament registrations when a team is disbanded"""
    
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
        if new_status != TeamStatus.DISBANDED.value:
            return  # Only act on disband transitions
        
        # Get all pending or approved tournament registrations
        stmt = select(TournamentRegistration).where(
            TournamentRegistration.team_id == entity.id,
            TournamentRegistration.status.in_([
                RegistrationStatus.PENDING, 
                RegistrationStatus.APPROVED
            ])
        )
        result = await session.execute(stmt)
        registrations = result.scalars().all()
        
        # Set registrations to WITHDRAWN
        withdrawn_reason = f"Team disbanded: {context.get('reason')}"
        for registration in registrations:
            LOG.info(f"Withdrawing team from tournament {registration.tournament_id} due to disbandment")
            registration.status = RegistrationStatus.WITHDRAWN
            registration.withdrawn_by = actor.id
            registration.withdrawn_at = datetime.now()
            registration.withdrawal_reason = withdrawn_reason
            session.add(registration)