from typing import List, Optional, Dict, Any
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from datetime import datetime
import uuid

from src.competitions.models.tournaments import Tournament, TournamentType, TournamentState
from src.competitions.models.rounds import Round
from src.competitions.models.fixtures import Fixture
from .schemas import TournamentCreate, TournamentUpdate, TournamentTeam, TournamentStandings
from src.audit.service import AuditService
from src.auth.models import Player

class TournamentServiceError(Exception):
    """Base exception for tournament service errors"""
    pass

class TournamentService:
    def __init__(self):
        self.audit_service = AuditService()

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
        if not isinstance(config['teams_advancing'], int) or config['teams_advancing'] < 1:
            raise TournamentServiceError("Teams advancing must be an integer greater than 0")

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