from typing import List, Optional, Dict
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from datetime import datetime, timedelta
import uuid

from competitions.models.rounds import Round, RoundType
from competitions.models.tournaments import Tournament, TournamentState
from competitions.models.fixtures import Fixture
from auth.models import Player
from audit.service import AuditService

class RoundServiceError(Exception):
    """Base exception for round service errors"""
    pass

class RoundService:
    def __init__(self):
        self.audit_service = AuditService()

    def _round_audit_details(self, round: Round) -> dict:
        """Extract audit details from a round operation"""
        return {
            "round_id": str(round.id),
            "tournament_id": str(round.tournament_id),
            "round_number": round.round_number,
            "type": round.type,
            "best_of": round.best_of,
            "start_date": round.start_date.isoformat() if round.start_date else None,
            "end_date": round.end_date.isoformat() if round.end_date else None,
            "status": round.status,
            "created_at": round.created_at.isoformat() if round.created_at else None,
            "updated_at": round.updated_at.isoformat() if round.updated_at else None
        }

    async def get_round(
        self,
        round_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[Round]:
        """Get a round by ID"""
        stmt = select(Round).where(Round.id == round_id)
        result = await session.exec(stmt)
        return result.first()

    async def get_tournament_rounds(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession,
        round_type: Optional[RoundType] = None
    ) -> List[Round]:
        """Get all rounds for a tournament"""
        stmt = select(Round).where(Round.tournament_id == tournament_id)
        if round_type:
            stmt = stmt.where(Round.type == round_type)
        stmt = stmt.order_by(Round.round_number)
        result = await session.exec(stmt)
        return result.all()

    @AuditService.audited_transaction(
        action_type="round_create",
        entity_type="round",
        details_extractor=_round_audit_details
    )
    async def create_round(
        self,
        tournament_id: uuid.UUID,
        round_type: RoundType,
        round_number: int,
        best_of: int,
        start_date: datetime,
        end_date: datetime,
        actor: Player,
        session: AsyncSession
    ) -> Round:
        """Create a new tournament round"""
        # Validate tournament exists and is in proper state
        tournament = await session.get(Tournament, tournament_id)
        if not tournament:
            raise RoundServiceError("Tournament not found")
        if tournament.state not in [TournamentState.NOT_STARTED, TournamentState.IN_PROGRESS]:
            raise RoundServiceError("Cannot create rounds for completed tournaments")

        # Validate round number is sequential
        existing_rounds = await self.get_tournament_rounds(tournament_id, session)
        if round_number <= len(existing_rounds):
            raise RoundServiceError("Round number must be sequential")

        # Create round
        round = Round(
            tournament_id=tournament_id,
            round_number=round_number,
            type=round_type,
            best_of=best_of,
            start_date=start_date,
            end_date=end_date,
            status="pending",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(round)
        return round

    @AuditService.audited_transaction(
        action_type="round_start",
        entity_type="round",
        details_extractor=_round_audit_details
    )
    async def start_round(
        self,
        round: Round,
        actor: Player,
        session: AsyncSession
    ) -> Round:
        """Start a tournament round"""
        # Validate round can be started
        if round.status != "pending":
            raise RoundServiceError("Round is not in pending state")

        # Validate previous round is complete (if not first round)
        if round.round_number > 1:
            prev_round = await self.get_round_by_number(
                round.tournament_id,
                round.round_number - 1,
                session
            )
            if prev_round and prev_round.status != "completed":
                raise RoundServiceError("Previous round must be completed first")

        round.status = "active"
        round.updated_at = datetime.now()
        session.add(round)
        return round

    @AuditService.audited_transaction(
        action_type="round_complete",
        entity_type="round",
        details_extractor=_round_audit_details
    )
    async def complete_round(
        self,
        round: Round,
        actor: Player,
        session: AsyncSession
    ) -> Round:
        """Complete a tournament round"""
        # Validate round can be completed
        if round.status != "active":
            raise RoundServiceError("Round is not active")

        # Validate all fixtures are completed
        fixtures = await self.get_round_fixtures(round.id, session)
        if not all(f.status == "completed" for f in fixtures):
            raise RoundServiceError("All fixtures must be completed")

        round.status = "completed"
        round.updated_at = datetime.now()
        session.add(round)
        return round

    async def get_round_by_number(
        self,
        tournament_id: uuid.UUID,
        round_number: int,
        session: AsyncSession
    ) -> Optional[Round]:
        """Get a specific round by number"""
        stmt = select(Round).where(
            Round.tournament_id == tournament_id,
            Round.round_number == round_number
        )
        result = await session.exec(stmt)
        return result.first()

    async def get_active_round(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[Round]:
        """Get the currently active round for a tournament"""
        stmt = select(Round).where(
            Round.tournament_id == tournament_id,
            Round.status == "active"
        )
        result = await session.exec(stmt)
        return result.first()

    async def get_round_fixtures(
        self,
        round_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Fixture]:
        """Get all fixtures for a round"""
        stmt = select(Fixture).where(Fixture.round_id == round_id)
        result = await session.exec(stmt)
        return result.all()

    async def validate_round_dates(
        self,
        tournament_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
        session: AsyncSession
    ) -> bool:
        """Validate round dates against tournament schedule"""
        tournament = await session.get(Tournament, tournament_id)
        if not tournament:
            raise RoundServiceError("Tournament not found")

        if start_date < tournament.registration_end:
            return False
        if end_date > tournament.scheduled_end_date:
            return False

        return True

    async def get_round_summary(
        self,
        round_id: uuid.UUID,
        session: AsyncSession
    ) -> Dict:
        """Get summary statistics for a round"""
        fixtures = await self.get_round_fixtures(round_id, session)
        total_fixtures = len(fixtures)
        completed_fixtures = sum(1 for f in fixtures if f.status == "completed")
        scheduled_fixtures = sum(1 for f in fixtures if f.status == "scheduled")
        cancelled_fixtures = sum(1 for f in fixtures if f.status == "cancelled")

        return {
            "total_fixtures": total_fixtures,
            "completed_fixtures": completed_fixtures,
            "scheduled_fixtures": scheduled_fixtures,
            "cancelled_fixtures": cancelled_fixtures,
            "completion_percentage": (completed_fixtures / total_fixtures * 100) if total_fixtures > 0 else 0
        }