from typing import List, Optional, Dict, Any
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from datetime import datetime
import uuid

from src.competitions.models.tournaments import Tournament, TournamentRegistration, TournamentType, TournamentState
from src.competitions.models.rounds import Round
from src.competitions.models.fixtures import Fixture
from src.teams.service import TeamService
from src.teams.models import Team
from .schemas import RegistrationReviewRequest, RegistrationStatus, RegistrationWithdrawRequest, TournamentCreate, TournamentRegistrationList, TournamentRegistrationRequest, TournamentUpdate, TournamentTeam, TournamentStandings
from src.audit.service import AuditService
from src.auth.models import Player

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
        """Retrieves a tournament by ID"""
        stmt = select(Tournament).where(Tournament.id == tournament_id)
        result = await session.exec(stmt)
        return result.first()

    async def get_tournaments_by_season(
        self,
        season_id: uuid.UUID,
        session: AsyncSession,
        include_completed: bool = True
    ) -> List[Tournament]:
        """Retrieves all tournaments for a season"""
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
        """Creates a new tournament"""
        # Validate tournament configuration based on type
        if tournament_data.type == TournamentType.REGULAR:
            self._validate_regular_tournament_config(tournament_data.format_config)
        elif tournament_data.type == TournamentType.KNOCKOUT:
            self._validate_knockout_tournament_config(tournament_data.format_config)

        tournament_dict = tournament_data.model_dump()
        new_tournament = Tournament(
            **tournament_dict,
            state=TournamentState.NOT_STARTED,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(new_tournament)
        return new_tournament

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
        """Updates tournament details"""
        if tournament.state != TournamentState.NOT_STARTED:
            raise TournamentServiceError("Cannot update tournament after it has started")

        update_dict = update_data.model_dump(exclude_unset=True)
        
        # Validate format config if it's being updated
        if 'format_config' in update_dict:
            if tournament.type == TournamentType.REGULAR:
                self._validate_regular_tournament_config(update_dict['format_config'])
            elif tournament.type == TournamentType.KNOCKOUT:
                self._validate_knockout_tournament_config(update_dict['format_config'])

        for key, value in update_dict.items():
            setattr(tournament, key, value)
            
        tournament.updated_at = datetime.now()
        session.add(tournament)
        return tournament

    @AuditService.audited_transaction(
        action_type="tournament_start",
        entity_type="tournament",
        details_extractor=_tournament_audit_details
    )
    async def start_tournament(
        self,
        tournament: Tournament,
        actor: Player,
        session: AsyncSession
    ) -> Tournament:
        """Starts a tournament"""
        if tournament.state != TournamentState.NOT_STARTED:
            raise TournamentServiceError("Tournament has already started")

        # Additional validation could go here
        # - Check minimum number of teams
        # - Verify all teams have minimum roster size
        # - etc.

        tournament.state = TournamentState.IN_PROGRESS
        tournament.updated_at = datetime.now()
        session.add(tournament)
        return tournament

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

    def _validate_regular_tournament_config(self, config: Dict[str, Any]):
        """Validates configuration for regular tournament format"""
        required_keys = {'group_size', 'teams_per_group', 'teams_advancing'}
        missing_keys = required_keys - set(config.keys())
        if missing_keys:
            raise TournamentServiceError(f"Missing required configuration keys: {missing_keys}")

        # Additional validation logic for regular tournament format
        if not isinstance(config['group_size'], int) or config['group_size'] < 2:
            raise TournamentServiceError("Group size must be an integer greater than 1")
        if not isinstance(config['teams_per_group'], int) or config['teams_per_group'] < 2:
            raise TournamentServiceError("Teams per group must be an integer greater than 1")
        # teams_advancing is optional, defaults to all teams (-1)
        if 'teams_advancing' in config:
            if not isinstance(config['teams_advancing'], int) or (config['teams_advancing'] != -1 and config['teams_advancing'] < 1):
                raise TournamentServiceError("Teams advancing must be -1 (all teams) or a positive integer")

    def _validate_knockout_tournament_config(self, config: Dict[str, Any]):
        """Validates configuration for knockout tournament format"""
        required_keys = {'seeding_type', 'third_place_playoff'}
        missing_keys = required_keys - set(config.keys())
        if missing_keys:
            raise TournamentServiceError(f"Missing required configuration keys: {missing_keys}")

        # Additional validation logic for knockout tournament format
        valid_seeding_types = {'random', 'group_position', 'elo'}
        if config['seeding_type'] not in valid_seeding_types:
            raise TournamentServiceError(f"Invalid seeding type. Must be one of: {valid_seeding_types}")
        if not isinstance(config['third_place_playoff'], bool):
            raise TournamentServiceError("Third place playoff must be a boolean")

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