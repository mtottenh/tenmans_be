from typing import List, Optional, Dict, Any
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from datetime import datetime
import uuid

from competitions.base_schemas import FixtureStatus
from competitions.models.tournaments import Tournament, TournamentRegistration, TournamentType, TournamentState
from competitions.models.rounds import Round
from competitions.models.fixtures import Fixture
from competitions.tournament.standings import get_standings_calculator
from matches.service import MatchService
from teams.service import TeamService
from teams.models import Team
from .schemas import RegistrationReviewRequest, RegistrationStatus, RegistrationWithdrawRequest, TournamentCreate, TournamentRegistrationList, TournamentRegistrationRequest, TournamentUpdate, TournamentTeam, TournamentStandings
from audit.service import AuditService
from auth.models import Player
from .generation.strategies import get_generation_strategy, GenerationError
from .generation.validators import TournamentValidator, ValidationError

class TournamentServiceError(Exception):
    """Base exception for tournament service errors"""
    pass

class RegistrationError(Exception):
    """Base exception for registration errors"""
    pass

class TournamentService:
    def __init__(self):
        self.audit_service = AuditService()
        self.team_service = TeamService()
        self.match_service = MatchService()
        self.validator = TournamentValidator()

    def _tournament_audit_details(self, tournament: Tournament) -> dict:
        """Extracts audit details from a tournament operation"""
        return {
            "tournament_id": str(tournament.id),
            "tournament_name": tournament.name,
            "tournament_type": tournament.type,
            "tournament_state": tournament.state,
            "season_id": str(tournament.season_id),
            "created_at": tournament.created_at.isoformat() if tournament.created_at else None,
            "updated_at": tournament.updated_at.isoformat() if tournament.updated_at else None
        }

 
    async def get_tournament(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession
    ) -> Optional[Tournament]:
        """Retrieve a tournament by ID"""
        stmt = select(Tournament).where(Tournament.id == tournament_id)
        result = await session.exec(stmt)
        return result.first()

    async def get_tournaments_by_season(
        self,
        season_id: uuid.UUID,
        session: AsyncSession,
        include_completed: bool = True
    ) -> List[Tournament]:
        """Retrieve all tournaments for a season"""
        stmt = select(Tournament).where(Tournament.season_id == season_id)
        if not include_completed:
            stmt = stmt.where(Tournament.state != TournamentState.COMPLETED)
        stmt = stmt.order_by(desc(Tournament.created_at))
        result = await session.exec(stmt)
        return result.all()

    @AuditService.audited_transaction(
        action_type="tournament_create",
        entity_type="tournament",
        details_extractor=_tournament_audit_details
    )
    async def create_tournament(
        self,
        tournament_data: TournamentCreate,
        actor: Player,
        session: AsyncSession
    ) -> Tournament:
        """Create a new tournament"""
        try:
            # Validate configuration using validator
            self.validator.validate_tournament_config(tournament_data)
            
            tournament_dict = tournament_data.model_dump()
            new_tournament = Tournament(
                **tournament_dict,
                state=TournamentState.NOT_STARTED,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(new_tournament)
            return new_tournament
            
        except ValidationError as e:
            raise TournamentServiceError(str(e))

    @AuditService.audited_transaction(
        action_type="tournament_update",
        entity_type="tournament",
        details_extractor=_tournament_audit_details
    )
    async def update_tournament(
        self,
        tournament: Tournament,
        update_data: TournamentUpdate,
        actor: Player,
        session: AsyncSession
    ) -> Tournament:
        """Update tournament details"""
        if tournament.state != TournamentState.NOT_STARTED:
            raise TournamentServiceError("Cannot update tournament after it has started")

        try:
            # Validate updated configuration
            if 'format_config' in update_data.model_dump(exclude_unset=True):
                self.validator.validate_tournament_config({
                    **tournament.model_dump(),
                    **update_data.model_dump(exclude_unset=True)
                })
            
            # Apply updates
            update_dict = update_data.model_dump(exclude_unset=True)
            for key, value in update_dict.items():
                setattr(tournament, key, value)
                
            tournament.updated_at = datetime.now()
            session.add(tournament)
            return tournament
            
        except ValidationError as e:
            raise TournamentServiceError(str(e))

    # Tournament lifecycle methods
    @AuditService.audited_transaction(
        action_type="tournament_generate",
        entity_type="tournament",
        details_extractor=_tournament_audit_details
    )
    async def generate_tournament_structure(
        self,
        tournament_id: uuid.UUID,
        actor: Player,
        session: AsyncSession
    ) -> Tournament:
        """Generate tournament structure including rounds and fixtures"""
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError("Tournament not found")
            
        if tournament.state != TournamentState.REGISTRATION_CLOSED:
            raise TournamentServiceError(
                "Tournament must be in REGISTRATION_CLOSED state for generation"
            )

        # Get registered teams
        teams = await self._get_registered_teams(tournament, session)
        
        try:
            # Validate tournament setup
            self.validator.validate_tournament_config(tournament)
            self.validator.validate_tournament_dates(tournament)
            self.validator.validate_teams(teams, tournament)
            
            # Get generation strategy and generate structure
            strategy = get_generation_strategy(tournament.type)
            rounds = await strategy.generate_rounds(tournament, teams, session)
            
            # Validate rounds
            self.validator.validate_round_dates(rounds, tournament)
            
            # Save rounds
            session.add_all(rounds)
            await session.flush()
            
            # Generate and save fixtures
            all_fixtures = []
            for round in rounds:
                fixtures = await strategy.generate_fixtures(
                    tournament,
                    round,
                    teams,
                    session
                )
                all_fixtures.extend(fixtures)
            
            session.add_all(all_fixtures)
            
            # Update tournament state
            tournament.state = TournamentState.NOT_STARTED
            tournament.actual_start_date = rounds[0].start_date
            tournament.updated_at = datetime.now()
            
            session.add(tournament)
            return tournament
            
        except (ValidationError, GenerationError) as e:
            raise TournamentServiceError(str(e))


    @AuditService.audited_transaction(
        action_type="tournament_complete",
        entity_type="tournament",
        details_extractor=_tournament_audit_details
    )
    async def complete_tournament(
        self,
        tournament: Tournament,
        actor: Player,
        session: AsyncSession
    ) -> Tournament:
        """Marks a tournament as completed"""
        if tournament.state != TournamentState.IN_PROGRESS:
            raise TournamentServiceError("Can only complete an in-progress tournament")

        # Additional validation could go here
        # - Verify all matches are completed
        # - Calculate final standings
        # - etc.

        tournament.state = TournamentState.COMPLETED
        tournament.updated_at = datetime.now()
        session.add(tournament)
        return tournament

    @AuditService.audited_transaction(
        action_type="tournament_cancel",
        entity_type="tournament",
        details_extractor=_tournament_audit_details
    )
    async def cancel_tournament(
        self,
        tournament: Tournament,
        actor: Player,
        session: AsyncSession
    ) -> Tournament:
        """Cancels a tournament"""
        if tournament.state == TournamentState.COMPLETED:
            raise TournamentServiceError("Cannot cancel a completed tournament")

        tournament.state = TournamentState.CANCELLED
        tournament.updated_at = datetime.now()
        session.add(tournament)
        return tournament


    async def get_tournament_standings(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession
    ) -> TournamentStandings:
        """Gets current tournament standings"""
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError("Tournament not found")

        # Logic to calculate standings based on tournament type
        if tournament.type == TournamentType.REGULAR:
            return await self._get_regular_tournament_standings(tournament, session)
        elif tournament.type == TournamentType.KNOCKOUT:
            return await self._get_knockout_tournament_standings(tournament, session)
        else:
            raise TournamentServiceError(f"Standings not available for tournament type: {tournament.type}")

    async def _get_regular_tournament_standings(
        self,
        tournament: Tournament,
        session: AsyncSession
    ) -> TournamentStandings:
        """Calculates standings for regular tournament format"""
        # Implementation for regular tournament standings
        # This would:
        # 1. Get all matches in the current group stage
        # 2. Calculate points for each team
        # 3. Sort teams by points and other criteria
        pass

    async def _get_knockout_tournament_standings(
        self,
        tournament: Tournament,
        session: AsyncSession
    ) -> TournamentStandings:
        """Calculates standings for knockout tournament format"""
        # Implementation for knockout tournament standings
        # This would:
        # 1. Determine the current round
        # 2. Track which teams have advanced/been eliminated
        # 3. Calculate current positions
        pass

    def _registration_audit_details(self, registration) -> dict:
        """Extract audit details for registration operations"""
        return {
            "registration_id": str(registration.id),
            "tournament_id": str(registration.tournament_id),
            "team_id": str(registration.team_id),
            "status": registration.status,
            "requested_at": registration.requested_at.isoformat(),
            "reviewed_at": registration.reviewed_at.isoformat() if registration.reviewed_at else None,
            "withdrawn_at": registration.withdrawn_at.isoformat() if registration.withdrawn_at else None
        }

    async def get_registration(
        self,
        tournament_id: uuid.UUID,
        registration_id: uuid.UUID,
        session: AsyncSession
    ):
        """Get a specific tournament registration"""
        stmt = select(TournamentRegistration).where(
            TournamentRegistration.tournament_id == tournament_id,
            TournamentRegistration.id == registration_id
        )
        result = await session.exec(stmt)
        return result.first()

    async def get_registrations(
        self,
        tournament_id: uuid.UUID,
        status: Optional[RegistrationStatus],
        session: AsyncSession
    ) -> TournamentRegistrationList:
        """Get all registrations for a tournament, optionally filtered by status"""
        stmt = select(TournamentRegistration).where(
            TournamentRegistration.tournament_id == tournament_id
        )
        if status:
            stmt = stmt.where(TournamentRegistration.status == status)
        
        result = await session.exec(stmt)
        registrations = result.all()
        
        # Calculate summary stats
        total_registered = len([r for r in registrations 
                              if r.status == RegistrationStatus.APPROVED])
        total_pending = len([r for r in registrations 
                           if r.status == RegistrationStatus.PENDING])
        
        return TournamentRegistrationList(
            total_registered=total_registered,
            total_pending=total_pending,
            registrations=registrations
        )

    @AuditService.audited_transaction(
        action_type="tournament_registration_request",
        entity_type="tournament_registration",
        details_extractor=_registration_audit_details
    )
    async def request_registration(
        self,
        tournament_id: uuid.UUID,
        registration_request: TournamentRegistrationRequest,
        actor: Player,
        session: AsyncSession
    ) -> TournamentRegistration:
        """Request registration in a tournament"""
        # Get tournament and team
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise RegistrationError("Tournament not found")
            
        team = await self.team_service.get_team_by_id(
            registration_request.team_id,
            session
        )
        if not team:
            raise RegistrationError("Team not found")
            
        # Validate registration is allowed
        await self._validate_registration_request(
            tournament,
            team,
            actor,
            session
        )
        
        # Create registration
        registration = TournamentRegistration(
            tournament_id=tournament_id,
            team_id=team.id,
            status=RegistrationStatus.PENDING,
            requested_by=actor.uid,
            requested_at=datetime.now(),
            notes=registration_request.notes
        )
        
        session.add(registration)
        return registration

    @AuditService.audited_transaction(
        action_type="tournament_registration_review",
        entity_type="tournament_registration",
        details_extractor=_registration_audit_details
    )
    async def review_registration(
        self,
        tournament_id: uuid.UUID,
        registration_id: uuid.UUID,
        review: RegistrationReviewRequest,
        actor: Player,
        session: AsyncSession
    ) -> TournamentRegistration:
        """Review a tournament registration request"""
        registration = await self.get_registration(
            tournament_id,
            registration_id,
            session
        )
        if not registration:
            raise RegistrationError("Registration not found")
            
        if registration.status != RegistrationStatus.PENDING:
            raise RegistrationError("Can only review pending registrations")
            
        # Update registration
        registration.status = review.status
        registration.reviewed_by = actor.uid
        registration.reviewed_at = datetime.now()
        registration.review_notes = review.notes
        
        session.add(registration)
        return registration

    @AuditService.audited_transaction(
        action_type="tournament_registration_withdraw",
        entity_type="tournament_registration",
        details_extractor=_registration_audit_details
    )
    async def withdraw_registration(
        self,
        tournament_id: uuid.UUID,
        registration_id: uuid.UUID,
        withdrawal: RegistrationWithdrawRequest,
        actor: Player,
        session: AsyncSession
    ) -> TournamentRegistration:
        """Withdraw from a tournament"""
        registration = await self.get_registration(
            tournament_id,
            registration_id,
            session
        )
        if not registration:
            raise RegistrationError("Registration not found")
            
        tournament = await self.get_tournament(tournament_id, session)
        
        # Verify actor is team captain
        is_captain = await self.team_service.player_is_team_captain(
            actor,
            registration.team,
            session
        )
        if not is_captain:
            raise RegistrationError("Only team captains can withdraw from tournaments")
            
        # Handle withdrawal based on tournament state
        if tournament.state == TournamentState.REGISTRATION_OPEN:
            # Simple withdrawal before registration closes
            registration.status = RegistrationStatus.WITHDRAWN
        elif tournament.state in [TournamentState.REGISTRATION_CLOSED, 
                                TournamentState.IN_PROGRESS]:
            # Withdrawal after registration closes - handle forfeits
            registration.status = RegistrationStatus.WITHDRAWN
            # TODO: Integration with fixture service to handle forfeits
        else:
            raise RegistrationError(
                "Cannot withdraw in current tournament state"
            )
            
        registration.withdrawn_by = actor.uid
        registration.withdrawn_at = datetime.now()
        registration.withdrawal_reason = withdrawal.reason
        
        session.add(registration)
        return registration

    async def _validate_registration_request(
        self,
        tournament: Tournament,
        team: Team,
        actor: Player,
        session: AsyncSession
    ):
        """Validate a registration request"""
        # Check tournament state
        if tournament.state != TournamentState.REGISTRATION_OPEN:
            if (tournament.state == TournamentState.REGISTRATION_CLOSED and
                tournament.allow_late_registration and
                datetime.now() <= tournament.late_registration_end):
                pass  # Allow late registration
            else:
                raise RegistrationError("Tournament registration is not open")
                
        # Check if team is already registered
        existing = await session.exec(
            select(TournamentRegistration).where(
                TournamentRegistration.tournament_id == tournament.id,
                TournamentRegistration.team_id == team.id,
                TournamentRegistration.status.in_([
                    RegistrationStatus.PENDING,
                    RegistrationStatus.APPROVED
                ])
            )
        )
        if existing.first():
            raise RegistrationError("Team is already registered")
            
        # Verify actor is team captain
        is_captain = await self.team_service.player_is_team_captain(
            actor,
            team,
            session
        )
        if not is_captain:
            raise RegistrationError("Only team captains can register for tournaments")
            
        # Check team size requirements
        roster_size = await self.team_service.get_active_roster_size(team, session)
        if roster_size < tournament.min_team_size:
            raise RegistrationError(
                f"Team must have at least {tournament.min_team_size} players"
            )
            
        # Check maximum registrations not exceeded
        current_registrations = await session.exec(
            select(TournamentRegistration).where(
                TournamentRegistration.tournament_id == tournament.id,
                TournamentRegistration.status == RegistrationStatus.APPROVED
            )
        )
        if len(current_registrations.all()) >= tournament.max_teams:
            raise RegistrationError("Tournament has reached maximum team capacity")
    async def _get_registered_teams(
        self,
        tournament: Tournament,
        session: AsyncSession
    ) -> List[Team]:
        """Get all teams registered for the tournament"""
        stmt = select(Team).join(
            tournament.registrations
        ).where(
            tournament.registrations.status == 'approved'
        )
        result = await session.exec(stmt)
        return result.all()

    @AuditService.audited_transaction(
        action_type="tournament_generate",
        entity_type="tournament",
        details_extractor=_tournament_audit_details
    )
   
    async def start_tournament(
        self,
        tournament_id: uuid.UUID,
        actor: Player,
        session: AsyncSession
    ) -> Tournament:
        """Start a tournament"""
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError("Tournament not found")

        if tournament.state != TournamentState.NOT_STARTED:
            raise TournamentServiceError(
                "Tournament must be in NOT_STARTED state to begin"
            )

        # Get first round
        first_round = await self._get_round_by_number(tournament.id, 1, session)
        if not first_round:
            raise TournamentServiceError("No rounds found for tournament")

        # Update tournament state
        tournament.state = TournamentState.IN_PROGRESS
        tournament.actual_start_date = datetime.now()
        tournament.updated_at = datetime.now()

        # Activate first round
        first_round.status = "active"
        
        session.add(tournament)
        session.add(first_round)
        return tournament

    async def complete_round(
        self,
        tournament_id: uuid.UUID,
        round_number: int,
        actor: Player,
        session: AsyncSession
    ) -> Tournament:
        """Complete a tournament round and progress to next if available"""
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError("Tournament not found")

        current_round = await self._get_round_by_number(
            tournament.id,
            round_number,
            session
        )
        if not current_round:
            raise TournamentServiceError("Round not found")

        # Verify all fixtures are completed
        fixtures = await self._get_round_fixtures(current_round.id, session)
        if not all(f.status in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED] 
                  for f in fixtures):
            raise TournamentServiceError("All fixtures must be completed")

        # Complete current round
        current_round.status = "completed"
        session.add(current_round)

        # Get next round
        next_round = await self._get_round_by_number(
            tournament.id,
            round_number + 1,
            session
        )

        if next_round:
            # Start next round
            next_round.status = "active"
            session.add(next_round)

            if tournament.type == TournamentType.KNOCKOUT:
                # Generate fixtures for next knockout round
                strategy = get_generation_strategy(tournament.type)
                winning_teams = await self._get_round_winners(current_round.id, session)
                
                fixtures = await strategy.generate_fixtures(
                    tournament,
                    next_round,
                    winning_teams,
                    session
                )
                session.add_all(fixtures)
        else:
            # No more rounds, complete tournament
            tournament.state = TournamentState.COMPLETED
            tournament.actual_end_date = datetime.now()
            tournament.updated_at = datetime.now()
            session.add(tournament)

        return tournament

    async def _get_round_by_number(
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

    async def _get_round_fixtures(
        self,
        round_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Fixture]:
        """Get all fixtures for a round"""
        stmt = select(Fixture).where(Fixture.round_id == round_id)
        result = await session.exec(stmt)
        return result.all()


    async def get_tournament_standings(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession
    ) -> TournamentStandings:
        """Get current tournament standings"""
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError("Tournament not found")

        try:
            calculator = get_standings_calculator(tournament.type)
            return await calculator.calculate_standings(
                tournament=tournament,
                match_service=self.match_service,
                session=session
            )
        except ValueError as e:
            raise TournamentServiceError(str(e))

    async def get_round_winners(
        self,
        round_id: uuid.UUID,
        session: AsyncSession
    ) -> List[Team]:
        """Get winning teams from a round's completed fixtures"""
        # Get all fixtures for the round
        fixtures = await self._get_round_fixtures(round_id, session)
        winners = []

        for fixture in fixtures:
            if fixture.status == FixtureStatus.FORFEITED:
                if not fixture.forfeit_winner:
                    raise TournamentServiceError(
                        f"Fixture {fixture.id} is forfeited but has no winner set"
                    )
                winner_id = fixture.forfeit_winner
            else:
                # TODO - This returns a list of Result objects which are *per-map*
                # Get match result from match service
                match_result = await self.match_service.get_match_results(
                    fixture.id,
                    session
                )
                if not match_result:
                    raise TournamentServiceError(
                        f"No result found for completed fixture {fixture.id}"
                    )
                winner_id = match_result.winner_id

            winner = await self.team_service.get_team_by_id(winner_id, session)
            winners.append(winner)

        return winners