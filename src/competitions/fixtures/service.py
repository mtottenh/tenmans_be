from typing import List, Optional, Tuple
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc, or_
from datetime import datetime, timedelta
import uuid

from competitions.models.tournaments import Tournament, TournamentState
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.rounds import Round, RoundType
from teams.models import Team
from auth.models import Player
from matches.models import Result, MatchPlayer
from audit.service import AuditService
from competitions.rounds.service import RoundService

from competitions.fixtures.schemas import (
    FixtureCreate,
    FixtureUpdate,
    FixtureReschedule,
    FixtureForfeit,
    MatchPlayerCreate
)

class FixtureServiceError(Exception):
    """Base exception for fixture service errors"""
    pass

class FixtureService:
    def __init__(self):
        self.audit_service = AuditService()
        self.round_service = RoundService()

    def _fixture_audit_details(self, fixture: Fixture) -> dict:
        """Extract audit details from a fixture operation"""
        return {
            "fixture_id": str(fixture.id),
            "tournament_id": str(fixture.tournament_id),
            "round_id": str(fixture.round_id),
            "team_1": str(fixture.team_1),
            "team_2": str(fixture.team_2),
            "status": fixture.status,
            "match_format": fixture.match_format,
            "scheduled_at": fixture.scheduled_at.isoformat() if fixture.scheduled_at else None,
            "created_at": fixture.created_at.isoformat() if fixture.created_at else None,
            "updated_at": fixture.updated_at.isoformat() if fixture.updated_at else None,
            "forfeit_winner": str(fixture.forfeit_winner) if fixture.forfeit_winner else None
        }

    async def get_fixture(
        self,
        fixture_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[Fixture]:
        """Get a fixture by ID"""
        stmt = select(Fixture).where(Fixture.id == fixture_id)
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_upcoming_fixtures(
        self,
        season_id: uuid.UUID,
        days: int,
        session: AsyncSession
    ) -> List[Fixture]:
        """
        Get upcoming fixtures for a season within the specified number of days
        
        Args:
            season_id: Season ID to filter fixtures
            days: Number of days to look ahead
            session: Database session
            
        Returns:
            List of fixtures ordered by scheduled date
        """
        now = datetime.now()
        end_date = now + timedelta(days=days)
        
        stmt = select(Fixture).where(
            Fixture.season_id == season_id,
            Fixture.status == FixtureStatus.SCHEDULED,
            Fixture.scheduled_at >= now,
            Fixture.scheduled_at <= end_date
        ).order_by(Fixture.scheduled_at)
        
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_tournament_fixtures(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession,
        status: Optional[FixtureStatus] = None
    ) -> List[Fixture]:
        """Get all fixtures for a tournament"""
        stmt = select(Fixture).where(Fixture.tournament_id == tournament_id)
        if status:
            stmt = stmt.where(Fixture.status == status)
        stmt = stmt.order_by(Fixture.scheduled_at)
        result = (await session.execute(stmt)).scalars()
        return result.all()

    @AuditService.audited_transaction(
        action_type="fixture_create",
        entity_type="fixture",
        details_extractor=_fixture_audit_details
    )
    async def create_fixture(
        self,
        fixture_data: FixtureCreate,
        actor: Player,
        session: AsyncSession
    ) -> Fixture:
        """Create a new fixture"""
        # Validate tournament state
        tournament = await session.get(Tournament, fixture_data.tournament_id)
        if not tournament:
            raise FixtureServiceError("Tournament not found")
            
        if tournament.state not in [TournamentState.NOT_STARTED, TournamentState.IN_PROGRESS]:
            raise FixtureServiceError("Cannot create fixtures for completed tournaments")

        # Validate round through round service
        round = await self.round_service.get_round(fixture_data.round_id, session)
        if not round or round.tournament_id != tournament.id:
            raise FixtureServiceError("Invalid round for tournament")
            
        if round.status != "active":
            raise FixtureServiceError("Can only create fixtures for active rounds")

        # Validate teams exist
        team_1 = await session.get(Team, fixture_data.team_1)
        team_2 = await session.get(Team, fixture_data.team_2)
        if not team_1 or not team_2:
            raise FixtureServiceError("One or more teams not found")

        # Validate fixture dates against round schedule
        if not (round.start_date <= fixture_data.scheduled_at <= round.end_date):
            raise FixtureServiceError("Fixture must be scheduled within round dates")

        fixture = Fixture(
            **fixture_data.model_dump(),
            status=FixtureStatus.SCHEDULED,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(fixture)
        return fixture

    @AuditService.audited_transaction(
        action_type="fixture_update",
        entity_type="fixture",
        details_extractor=_fixture_audit_details
    )
    async def update_fixture(
        self,
        fixture: Fixture,
        update_data: FixtureUpdate,
        actor: Player,
        session: AsyncSession
    ) -> Fixture:
        """Update fixture details"""
        if fixture.status in [FixtureStatus.COMPLETED, FixtureStatus.CANCELLED]:
            raise FixtureServiceError("Cannot update completed or cancelled fixtures")

        # If updating scheduled time, validate against round dates
        if update_data.scheduled_at:
            round = await self.round_service.get_round(fixture.round_id, session)
            if not round:
                raise FixtureServiceError("Round not found")
                
            if not (round.start_date <= update_data.scheduled_at <= round.end_date):
                raise FixtureServiceError("Fixture must be scheduled within round dates")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(fixture, key, value)

        fixture.updated_at = datetime.now()
        session.add(fixture)
        return fixture

    @AuditService.audited_transaction(
        action_type="fixture_reschedule",
        entity_type="fixture",
        details_extractor=_fixture_audit_details
    )
    async def reschedule_fixture(
        self,
        fixture: Fixture,
        reschedule_data: FixtureReschedule,
        actor: Player,
        session: AsyncSession
    ) -> Fixture:
        """Reschedule a fixture"""
        if fixture.status in [FixtureStatus.COMPLETED, FixtureStatus.CANCELLED]:
            raise FixtureServiceError("Cannot reschedule completed or cancelled fixtures")

        # Validate new date against round schedule
        round = await self.round_service.get_round(fixture.round_id, session)
        if not round:
            raise FixtureServiceError("Round not found")
            
        if not (round.start_date <= reschedule_data.scheduled_at <= round.end_date):
            raise FixtureServiceError("Fixture must be scheduled within round dates")

        fixture.rescheduled_from = fixture.scheduled_at
        fixture.scheduled_at = reschedule_data.scheduled_at
        fixture.rescheduled_by = reschedule_data.rescheduled_by
        fixture.reschedule_reason = reschedule_data.reschedule_reason
        fixture.updated_at = datetime.now()

        session.add(fixture)
        return fixture

    @AuditService.audited_transaction(
        action_type="fixture_forfeit",
        entity_type="fixture",
        details_extractor=_fixture_audit_details
    )
    async def forfeit_fixture(
        self,
        fixture: Fixture,
        forfeit_data: FixtureForfeit,
        actor: Player,
        session: AsyncSession
    ) -> Fixture:
        """Mark a fixture as forfeited"""
        if fixture.status == FixtureStatus.COMPLETED:
            raise FixtureServiceError("Cannot forfeit completed fixtures")

        if forfeit_data.forfeit_winner not in [fixture.team_1, fixture.team_2]:
            raise FixtureServiceError("Forfeit winner must be one of the fixture teams")

        fixture.status = FixtureStatus.FORFEITED
        fixture.forfeit_winner = forfeit_data.forfeit_winner
        fixture.forfeit_reason = forfeit_data.forfeit_reason
        fixture.updated_at = datetime.now()

        session.add(fixture)

        # Check if round can be completed
        round = await self.round_service.get_round(fixture.round_id, session)
        if round and await self._check_round_completion(round, session):
            await self.round_service.complete_round(round, actor, session)

        return fixture

    @AuditService.audited_transaction(
        action_type="fixture_complete",
        entity_type="fixture",
        details_extractor=_fixture_audit_details
    )
    async def complete_fixture(
        self,
        fixture: Fixture,
        actor: Player,
        session: AsyncSession
    ) -> Fixture:
        """Mark a fixture as completed"""
        if fixture.status != FixtureStatus.IN_PROGRESS:
            raise FixtureServiceError("Can only complete fixtures that are in progress")

        fixture.status = FixtureStatus.COMPLETED
        fixture.updated_at = datetime.now()
        session.add(fixture)

        # Check if round can be completed
        round = await self.round_service.get_round(fixture.round_id, session)
        if round and await self._check_round_completion(round, session):
            await self.round_service.complete_round(round, actor, session)

        return fixture

    async def _check_round_completion(
        self,
        round: Round,
        session: AsyncSession
    ) -> bool:
        """Check if all fixtures in a round are completed or forfeited"""
        fixtures = await self.round_service.get_round_fixtures(round.id, session)
        return all(f.status in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED] 
                  for f in fixtures)

    async def get_team_fixtures(
        self,
        team_id: uuid.UUID,
        session: AsyncSession,
        status: Optional[FixtureStatus] = None
    ) -> List[Fixture]:
        """Get all fixtures for a team"""
        stmt = select(Fixture).where(
            or_(
                Fixture.team_1 == team_id,
                Fixture.team_2 == team_id
            )
        )
        if status:
            stmt = stmt.where(Fixture.status == status)
        stmt = stmt.order_by(Fixture.scheduled_at)
        result = (await session.execute(stmt)).scalars()
        return result.all()

    @AuditService.audited_transaction(
        action_type="fixture_add_player",
        entity_type="match_player"
    )
    async def add_match_player(
        self,
        player_data: MatchPlayerCreate,
        actor: Player,
        session: AsyncSession
    ) -> MatchPlayer:
        """Add a player to a match"""
        fixture = await self.get_fixture(player_data.fixture_id, session)
        if not fixture:
            raise FixtureServiceError("Fixture not found")

        if fixture.status != FixtureStatus.SCHEDULED:
            raise FixtureServiceError("Can only add players to scheduled fixtures")

        if player_data.team_id not in [fixture.team_1, fixture.team_2]:
            raise FixtureServiceError("Player must be assigned to one of the fixture teams")

        match_player = MatchPlayer(
            **player_data.model_dump(),
            created_at=datetime.now()
        )
        session.add(match_player)
        return match_player

    async def get_upcoming_fixtures(
        self,
        days: int,
        session: AsyncSession
    ) -> List[Fixture]:
        """Get fixtures scheduled in the next X days"""
        end_date = datetime.now() + timedelta(days=days)
        stmt = select(Fixture).where(
            Fixture.status == FixtureStatus.SCHEDULED,
            Fixture.scheduled_at <= end_date
        ).order_by(Fixture.scheduled_at)
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_fixture_with_details(
        self,
        fixture_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[Fixture]:
        """Get fixture with related entities loaded"""
        stmt = select(Fixture).where(
            Fixture.id == fixture_id
        ).join(Tournament).join(Round).join(Team, Fixture.team_1 == Team.id)
        result = (await session.execute(stmt)).scalars()
        return result.first()