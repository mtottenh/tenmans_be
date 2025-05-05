# availability/service.py
from typing import Dict, List, Optional, Tuple
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, and_, or_
from datetime import datetime, timedelta, date
import uuid

from audit.context import AuditContext
from audit.models import AuditEventType
from audit.service import AuditService
from auth.models import Player
from competitions.models.scheduling import (
    PlayerAvailability,
    TeamAvailability,
    ScheduleSuggestion,
    ScheduleConflict,
    AvailabilityType,
    AvailabilityStatus
)
from teams.models import Team, Roster
from teams.base_schemas import RosterStatus
from status.service import StatusTransitionService

class AvailabilityServiceError(Exception):
    """Base exception for availability service errors"""
    pass

class AvailabilityService:
    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        status_transition_service: Optional[StatusTransitionService] = None
    ):
        self.audit_service = audit_service or AuditService()
        self.status_transition_service = status_transition_service or StatusTransitionService()

    def _availability_audit_details(self, availability: PlayerAvailability, context: Dict) -> dict:
        """Extract audit details from an availability operation"""
        return {
            "availability_id": str(availability.id),
            "player_id": str(availability.player_id),
            "tournament_id": str(availability.tournament_id) if availability.tournament_id else None,
            "start_time": availability.start_time.isoformat(),
            "end_time": availability.end_time.isoformat(),
            "availability_type": availability.availability_type,
            "status": availability.status,
            "is_substitute": availability.is_substitute,
        }

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type="PlayerAvailability",
        details_extractor=_availability_audit_details
    )
    async def add_availability(
        self,
        player: Player,
        availability_data: Dict,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None
    ) -> PlayerAvailability:
        """Add player availability"""
        # Validate that player can only edit their own availability
        if player.id != actor.id:
            raise AvailabilityServiceError("Players can only modify their own availability")

        availability = PlayerAvailability(
            player_id=player.id,
            tournament_id=availability_data.get('tournament_id'),
            start_time=availability_data['start_time'],
            end_time=availability_data['end_time'],
            availability_type=availability_data['availability_type'],
            is_substitute=availability_data.get('is_substitute', False),
            notes=availability_data.get('notes'),
            recurring=availability_data.get('recurring', False),
            recurring_pattern=availability_data.get('recurring_pattern'),
            status=AvailabilityStatus.ACTIVE,
        )
        
        session.add(availability)
        await session.flush()
        return availability

    async def update_availability_status(
        self,
        availability: PlayerAvailability,
        new_status: AvailabilityStatus,
        actor: Player,
        session: AsyncSession,
        reason: str = "Status update",
        audit_context: Optional[AuditContext] = None
    ) -> PlayerAvailability:
        """Update availability status using status transition service"""
        return await self.status_transition_service.transition_status(
            entity=availability,
            new_status=new_status,
            reason=reason,
            actor=actor,
            session=session,
            audit_context=audit_context
        )

    async def get_player_availability(
        self,
        player: Player,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        tournament_id: Optional[uuid.UUID] = None,
        session: AsyncSession = None
    ) -> List[PlayerAvailability]:
        """Get player availability within date range"""
        stmt = select(PlayerAvailability).where(
            PlayerAvailability.player_id == player.id,
            PlayerAvailability.status == AvailabilityStatus.ACTIVE
        )

        if start_date:
            stmt = stmt.where(PlayerAvailability.end_time >= start_date)
        if end_date:
            stmt = stmt.where(PlayerAvailability.start_time <= end_date)
        if tournament_id:
            stmt = stmt.where(PlayerAvailability.tournament_id == tournament_id)

        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_team_availability(
        self,
        team_id: uuid.UUID,
        date: date,
        tournament_id: uuid.UUID,
        session: AsyncSession
    ) -> TeamAvailability:
        """Get aggregated team availability for a specific date"""
        # Get team roster
        stmt = select(Roster).where(
            Roster.team_id == team_id,
            Roster.status == RosterStatus.ACTIVE
        )
        result = await session.execute(stmt)
        roster_players = result.scalars().all()

        available_players = []
        maybe_players = []
        unavailable_players = []
        available_substitutes = []

        # Check each player's availability
        for roster in roster_players:
            player_availability = await self.get_player_availability(
                player=roster.player,
                start_date=datetime.combine(date, datetime.min.time()),
                end_date=datetime.combine(date, datetime.max.time()),
                tournament_id=tournament_id,
                session=session
            )

            if not player_availability:
                unavailable_players.append(roster.player_id)
                continue

            # Aggregate availability types
            has_available = any(a.availability_type == AvailabilityType.AVAILABLE for a in player_availability)
            has_maybe = any(a.availability_type == AvailabilityType.MAYBE for a in player_availability)
            has_unavailable = any(a.availability_type == AvailabilityType.UNAVAILABLE for a in player_availability)

            if has_unavailable:
                unavailable_players.append(roster.player_id)
            elif has_available:
                available_players.append(roster.player_id)
            elif has_maybe:
                maybe_players.append(roster.player_id)
            else:
                unavailable_players.append(roster.player_id)

        # Create or update team availability record
        stmt = select(TeamAvailability).where(
            TeamAvailability.team_id == team_id,
            TeamAvailability.tournament_id == tournament_id,
            TeamAvailability.date == date
        )
        result = await session.execute(stmt)
        team_availability = result.scalar_one_or_none()

        if not team_availability:
            team_availability = TeamAvailability(
                team_id=team_id,
                tournament_id=tournament_id,
                date=date
            )
            session.add(team_availability)

        team_availability.available_players = available_players
        team_availability.maybe_players = maybe_players
        team_availability.unavailable_players = unavailable_players
        team_availability.available_substitutes = available_substitutes
        team_availability.has_minimum_players = len(available_players) >= 5  # Assuming minimum 5 players
        team_availability.updated_at = datetime.now()

        return team_availability

    async def find_optimal_times(
        self,
        team_1_id: uuid.UUID,
        team_2_id: uuid.UUID,
        tournament_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
        session: AsyncSession
    ) -> List[ScheduleSuggestion]:
        """Find optimal scheduling times for two teams"""
        suggestions = []
        current_date = start_date.date()
        
        while current_date <= end_date.date():
            team_1_availability = await self.get_team_availability(
                team_1_id, current_date, tournament_id, session
            )
            team_2_availability = await self.get_team_availability(
                team_2_id, current_date, tournament_id, session
            )

            # Check if both teams have minimum players available
            if team_1_availability.has_minimum_players and team_2_availability.has_minimum_players:
                # Create suggestion for this date
                suggested_time = datetime.combine(current_date, datetime.min.time().replace(hour=19))  # 7 PM
                
                suggestion = ScheduleSuggestion(
                    fixture_id=None,  # Will be set when fixture is created
                    suggested_time=suggested_time,
                    confidence_score=self._calculate_confidence_score(team_1_availability, team_2_availability),
                    available_players_team1=len(team_1_availability.available_players),
                    available_players_team2=len(team_2_availability.available_players),
                    conflicts=[]
                )
                suggestions.append(suggestion)

            current_date += timedelta(days=1)

        return sorted(suggestions, key=lambda x: x.confidence_score, reverse=True)

    def _calculate_confidence_score(
        self,
        team_1_availability: TeamAvailability,
        team_2_availability: TeamAvailability
    ) -> float:
        """Calculate confidence score for a scheduling suggestion"""
        # Simple scoring: percentage of players available
        team_1_score = len(team_1_availability.available_players) / max(len(team_1_availability.available_players + team_1_availability.maybe_players + team_1_availability.unavailable_players), 1)
        team_2_score = len(team_2_availability.available_players) / max(len(team_2_availability.available_players + team_2_availability.maybe_players + team_2_availability.unavailable_players), 1)
        
        return (team_1_score + team_2_score) / 2.0

    async def check_conflicts(
        self,
        fixture_id: uuid.UUID,
        proposed_time: datetime,
        session: AsyncSession
    ) -> List[ScheduleConflict]:
        """Check for scheduling conflicts"""
        from competitions.models.fixtures import Fixture
        
        fixture = await session.get(Fixture, fixture_id)
        if not fixture:
            raise AvailabilityServiceError("Fixture not found")

        conflicts = []
        
        # Check team 1 availability
        team_1_availability = await self.get_team_availability(
            fixture.team_1,
            proposed_time.date(),
            fixture.tournament_id,
            session
        )
        
        if not team_1_availability.has_minimum_players:
            conflicts.append(ScheduleConflict(
                fixture_id=fixture_id,
                conflict_type="insufficient_players",
                description=f"Team 1 does not have minimum players available",
                severity="high",
                affected_players=team_1_availability.unavailable_players
            ))

        # Check team 2 availability
        team_2_availability = await self.get_team_availability(
            fixture.team_2,
            proposed_time.date(),
            fixture.tournament_id,
            session
        )
        
        if not team_2_availability.has_minimum_players:
            conflicts.append(ScheduleConflict(
                fixture_id=fixture_id,
                conflict_type="insufficient_players",
                description=f"Team 2 does not have minimum players available",
                severity="high",
                affected_players=team_2_availability.unavailable_players
            ))

        return conflicts

def create_availability_service(
    audit_service: Optional[AuditService] = None,
    status_transition_service: Optional[StatusTransitionService] = None
) -> AvailabilityService:
    audit_service = audit_service or AuditService()
    status_transition_service = status_transition_service or StatusTransitionService()
    return AvailabilityService(audit_service, status_transition_service)