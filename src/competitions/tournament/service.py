import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from audit.models import AuditEventType
from audit.service import AuditService
from auth.models import Player
from competitions.base_schemas import FixtureStatus, LeagueFormat, MapSelectionMethod
from competitions.map_pool.models import (
    MapPoolMap,
    MapPoolSelectionType,
    MapPoolStatus,
    MapPoolVote,
)
from competitions.map_pool.schemas import (
    MapPoolCreate,
    MapPoolVoteRequest,
    MapPoolVoteResponse,
)
from competitions.models.fixtures import Fixture
from competitions.models.linked_tournaments import LinkedTournament
from competitions.models.rounds import Round
from competitions.models.tournaments import (
    Tournament,
    TournamentRegistration,
    TournamentState,
    TournamentType,
)
from competitions.rounds.round_winner_service import RoundWinnerService
from competitions.rounds.service import RoundService
from competitions.tournament.standings import get_standings_calculator
from maps.schemas import TournamentMapPool
from matches.service import MatchService
from status.manager.tournament import initialize_tournament_status_manager
from status.service import StatusTransitionService
from status.transition_validator import TransitionError
from teams.models import Team
from teams.service.team import TeamService

from .generation.strategies import GenerationError, get_generation_strategy
from .generation.validators import TournamentValidator, ValidationError
from .schemas import (
    RegistrationReviewRequest,
    RegistrationStatus,
    RegistrationWithdrawRequest,
    TournamentBasicUpdate,
    TournamentConfigUpdate,
    TournamentCreate,
    TournamentRegistrationList,
    TournamentRegistrationRequest,
    TournamentStandings,
    TournamentWithStats,
)


LOG = logging.getLogger("uvicorn.error")


class TournamentServiceError(Exception):
    """Base exception for tournament service errors"""

    pass


class RegistrationError(Exception):
    """Base exception for registration errors"""

    pass


class TournamentService:
    def __init__(
        self,
        team_service: Optional[TeamService] = None,
        match_service: Optional[MatchService] = None,
        round_service: Optional[RoundService] = None,
        audit_service: Optional[AuditService] = None,
        status_transition_service: Optional[StatusTransitionService] = None,
        validator: Optional[TournamentValidator] = None,
    ):
        self.audit_service = audit_service or AuditService()
        self.team_service = team_service or TeamService()

        # Create round service with proper dependency injection
        self.round_service = round_service or RoundService(
            audit_service=self.audit_service,
            status_transition_service=status_transition_service,
            round_winner_service=RoundWinnerService(),
        )

        # Initialize status transition service and register tournament manager
        self.status_transition_service = (
            status_transition_service or StatusTransitionService()
        )
        tournament_status_manager = initialize_tournament_status_manager()
        self.status_transition_service.register_transition_manager(
            "Tournament", tournament_status_manager
        )

        self.match_service = match_service or MatchService()
        self.validator = validator or TournamentValidator()

    def _tournament_audit_details(self, tournament: Tournament, context: dict) -> dict:  # noqa: ARG002
        """Extracts audit details from a tournament operation"""
        return {
            "tournament_id": str(tournament.id),
            "tournament_name": tournament.name,
            "tournament_type": tournament.type,
            "tournament_status": tournament.status,
            "season_id": str(tournament.season_id),
            "created_at": tournament.created_at.isoformat()
            if tournament.created_at
            else None,
            "updated_at": tournament.updated_at.isoformat()
            if tournament.updated_at
            else None,
        }

    def _next_round_fixtures_audit_details(
        self, entity_or_result, context: dict) -> dict:
        """Extracts audit details from next round fixture generation"""
        # Handle both pre-execution (Tournament) and post-execution (List[Fixture]) cases
        if isinstance(entity_or_result, Tournament):
            # Pre-execution: entity is the tournament
            tournament = entity_or_result
            fixtures = None
        else:
            # Post-execution: result is the list of fixtures
            fixtures = entity_or_result
            # Get the tournament from the context parameters
            params = context.get("params", {})
            tournament = params.get("tournament")

        round_number = (
            context.get("params", {}).get("round_number")
            if context.get("params")
            else None
        )

        return {
            "tournament_id": str(tournament.id) if tournament else None,
            "tournament_name": tournament.name if tournament else None,
            "tournament_type": tournament.type if tournament else None,
            "round_number": round_number,
            "fixtures_generated": len(fixtures) if fixtures else 0,
            "fixture_ids": [str(f.id) for f in fixtures] if fixtures else [],
        }

    # Add helper method for audit details
    def _map_pool_audit_details(
        self, map_pool: TournamentMapPool, context: dict) -> dict:  # noqa: ARG002
        """Extract audit details from a map pool operation"""
        return {
            "map_pool_id": str(map_pool.id),
            "tournament_id": str(map_pool.tournament_id),
            "selection_type": map_pool.selection_type,
            "status": map_pool.status,
            "voting_start": map_pool.voting_start.isoformat()
            if map_pool.voting_start
            else None,
            "voting_end": map_pool.voting_end.isoformat()
            if map_pool.voting_end
            else None,
            "finalized_at": map_pool.finalized_at.isoformat()
            if map_pool.finalized_at
            else None,
        }

    def _map_vote_audit_details(self, vote: MapPoolVote, context: dict) -> dict:  # noqa: ARG002
        """Extract audit details from a map vote operation"""
        return {
            "vote_id": str(vote.id),
            "pool_id": str(vote.pool_id),
            "team_id": str(vote.team_id),
            "map_id": str(vote.map_id),
            "voted_at": vote.voted_at.isoformat(),
        }

    async def change_tournament_status(
        self,
        tournament: Tournament,
        new_status: TournamentState,
        reason: str,
        actor: Player,
        session: AsyncSession,
        entity_metadata: Optional[dict] = None,
    ) -> Tournament:
        """
        Change a tournament's status with validation and history tracking

        Args:
            tournament: Tournament to update
            new_status: New status to set
            reason: Reason for the change
            actor: User making the change
            entity_metadata: Additional metadata
            session: Database session
        """
        return await self.status_transition_service.transition_status(
            entity=tournament,
            new_status=new_status,
            reason=reason,
            actor=actor,
            entity_metadata=entity_metadata,
            session=session,
        )

    async def get_tournament(
        self, tournament_id: uuid.UUID, session: AsyncSession
    ) -> Optional[Tournament]:
        """Retrieve a tournament by ID"""
        stmt = select(Tournament).where(Tournament.id == tournament_id)
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_tournaments_by_season(
        self,
        season_id: uuid.UUID,
        session: AsyncSession,
        include_completed: bool = True,
    ) -> list[Tournament]:
        """Retrieve all tournaments for a season"""
        stmt = select(Tournament).where(Tournament.season_id == season_id)
        if not include_completed:
            stmt = stmt.where(Tournament.status != TournamentState.COMPLETED)
        stmt = stmt.order_by(desc(Tournament.created_at))
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def _get_active_tournaments(self, session: AsyncSession) -> list[Tournament]:
        query = (
            select(Tournament, Team)
            .where(Tournament.status == TournamentState.IN_PROGRESS)
            .where(TournamentRegistration.tournament_id == Tournament.id)
            .where(TournamentRegistration.team_id == Team.id)
        )
        return (await session.execute(query)).scalars().all

    async def get_tournaments(
        self,
        session: AsyncSession,
        status: Optional[list[TournamentState]] = None,
        season_id: Optional[uuid.UUID] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Tournament], int]:
        """
        Get tournaments with optional filters and pagination
        Returns tuple of (tournaments, total_count)
        """
        # Base query
        query = select(Tournament)

        # Apply filters
        if status:
            query = query.where(Tournament.status.in_(status))
        if season_id:
            query = query.where(Tournament.season_id == season_id)

        # Get total count before pagination
        count_query = select(func.count()).select_from(query)
        total = (await session.execute(count_query)).scalar()

        # Apply pagination
        query = query.offset(offset).limit(limit)

        # Execute query
        result = await session.execute(query)
        tournaments = result.scalars().all()

        return tournaments, total

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type="Tournament",
        details_extractor=_tournament_audit_details,
    )
    async def create_tournament(
        self,
        tournament_data: TournamentCreate,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Create a new tournament"""
        try:
            # Validate configuration using validator
            self.validator.validate_tournament_config(tournament_data)

            tournament_dict = tournament_data.model_dump(exclude={"initial_map_pool"})
            for field in [
                "registration_start",
                "registration_end",
                "scheduled_start_date",
                "scheduled_end_date",
                "late_registration_end",
            ]:
                if tournament_dict.get(field):
                    tournament_dict[field] = (
                        tournament_dict[field]
                        .astimezone(timezone.utc)
                        .replace(tzinfo=None)
                    )

            new_tournament = Tournament(
                **tournament_dict,
                state=TournamentState.NOT_STARTED,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(new_tournament)
            await session.flush()

            # Create initial map pool if specified and using admin-defined method
            if (
                tournament_data.map_selection_method
                == MapSelectionMethod.ADMIN_ASSIGNED
                and tournament_data.initial_map_pool
            ):
                map_pool = TournamentMapPool(
                    tournament_id=new_tournament.id,
                    selection_type=MapPoolSelectionType.ADMIN_DEFINED,
                    status=MapPoolStatus.FINALIZED,
                    finalized_at=datetime.now(timezone.utc),
                )
                session.add(map_pool)
                await session.flush()

                # Add maps to the pool
                for map_id in tournament_data.initial_map_pool:
                    pool_map = MapPoolMap(pool_id=map_pool.id, map_id=map_id)
                    session.add(pool_map)

            return new_tournament

        except ValidationError as e:
            raise TournamentServiceError(str(e)) from e

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Tournament",
        details_extractor=_tournament_audit_details,
    )
    async def update_tournament_basics(
        self,
        tournament: Tournament,
        update_data: TournamentBasicUpdate,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Update tournament details"""
        if tournament.status != TournamentState.NOT_STARTED:
            raise TournamentServiceError(
                "Cannot update tournament after it has started"
            )

        try:
            # Apply updates
            update_dict = update_data.model_dump(exclude_unset=True)
            for key, value in update_dict.items():
                setattr(tournament, key, value)

            tournament.updated_at = datetime.now(timezone.utc)
            session.add(tournament)
            return tournament

        except ValidationError as e:
            raise TournamentServiceError(str(e)) from e

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Tournament",
        details_extractor=_tournament_audit_details,
    )
    async def update_tournament_config(
        self,
        tournament: Tournament,
        config_update: TournamentConfigUpdate,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
    ) -> Tournament:
        """Update tournament configuration settings"""
        if tournament.status != TournamentState.NOT_STARTED:
            raise TournamentServiceError(
                "Cannot update configuration after tournament has started"
            )

        try:
            # Validate configuration changes
            updated_config = {
                **tournament.model_dump(),
                **config_update.model_dump(exclude_unset=True),
            }
            self.validator.validate_tournament_config(updated_config)

            # Apply updates
            update_dict = config_update.model_dump(exclude_unset=True)
            for key, value in update_dict.items():
                setattr(tournament, key, value)

            tournament.updated_at = datetime.now(timezone.utc)
            session.add(tournament)
            return tournament

        except ValidationError as e:
            raise TournamentServiceError(str(e)) from e

    # Tournament lifecycle methods

    # @AuditService.audited_transaction(
    #     action_type=AuditEventType.UPDATE,
    #     entity_type="Tournament",
    #     details_extractor=_tournament_audit_details
    # )
    async def link_tournaments(
        self,
        source_tournament_id: uuid.UUID,
        target_tournament_id: uuid.UUID,
        qualification_rules: dict[str, Any],
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
    ) -> LinkedTournament:
        """Link two tournaments for automatic qualification"""
        source = await self.get_tournament(source_tournament_id, session)
        target = await self.get_tournament(target_tournament_id, session)

        if not source or not target:
            raise TournamentServiceError("One or both tournaments not found")

        if source.type != TournamentType.REGULAR:
            raise TournamentServiceError("Source tournament must be a league")

        if target.type != TournamentType.KNOCKOUT:
            raise TournamentServiceError(
                "Target tournament must be a knockout tournament"
            )

        # Check if link already exists
        existing_link = await session.execute(
            select(LinkedTournament).where(
                LinkedTournament.source_tournament_id == source_tournament_id,
                LinkedTournament.target_tournament_id == target_tournament_id,
            )
        )
        if existing_link.scalar_one_or_none():
            raise TournamentServiceError("Tournaments are already linked")

        linked_tournament = LinkedTournament(
            source_tournament_id=source_tournament_id,
            target_tournament_id=target_tournament_id,
            qualification_rules=qualification_rules,
            created_at=datetime.now(timezone.utc),
        )

        session.add(linked_tournament)
        await session.commit()
        await session.refresh(linked_tournament)

        return linked_tournament

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Tournament",
        details_extractor=_tournament_audit_details,
    )
    async def cancel_tournament(
        self,
        tournament: Tournament,
        actor: Player,
        reason: str,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Cancels a tournament"""
        if tournament.status == TournamentState.COMPLETED:
            raise TournamentServiceError("Cannot cancel a completed tournament")

        # Update tournament state - this will trigger the cancellation pipeline
        tournament = await self.change_tournament_status(
            tournament=tournament,
            new_status=TournamentState.CANCELLED,
            reason=reason,
            actor=actor,
            session=session,
        )
        return tournament

    async def get_tournament_standings(
        self, tournament_id: uuid.UUID, session: AsyncSession
    ) -> TournamentStandings:
        """Get current tournament standings"""
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError("Tournament not found")

        try:
            calculator = get_standings_calculator(tournament.type)
            return await calculator.calculate_standings(
                tournament=tournament, session=session
            )
        except ValueError as e:
            raise TournamentServiceError(str(e)) from e

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Tournament",
        details_extractor=_tournament_audit_details,
        entity_param="tournament",  # Specify that 'tournament' parameter is the entity
    )
    async def generate_tournament_structure(
        self,
        tournament: Tournament,
        actor: Player,
        session: AsyncSession,
        regenerate: bool = False,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Generate tournament structure including rounds and fixtures"""
        if not tournament:
            raise TournamentServiceError("Tournament not provided")

        # Validate tournament state
        valid_states = [TournamentState.REGISTRATION_CLOSED]
        if regenerate:
            valid_states.append(TournamentState.NOT_STARTED)

        if tournament.status not in valid_states:
            raise TournamentServiceError(
                f"Tournament must be in {valid_states} state for generation"
            )

        # Get registered teams
        teams = await self._get_registered_teams(tournament, session)

        try:
            # Transition to NOT_STARTED with generation context
            tournament = await self.change_tournament_status(
                tournament=tournament,
                new_status=TournamentState.NOT_STARTED,
                reason="Generating tournament structure",
                actor=actor,
                entity_metadata={"regenerate": regenerate},
                session=session,
            )

            # Validate tournament setup
            self.validator.validate_tournament_config(tournament)
            self.validator.validate_tournament_dates(tournament)
            self.validator.validate_teams(teams, tournament)

            # Get generation strategy
            strategy = get_generation_strategy(tournament)

            # Generate rounds
            rounds = await strategy.generate_rounds(tournament, teams, session)

            # Validate rounds
            self.validator.validate_round_dates(rounds, tournament)

            # Save rounds
            session.add_all(rounds)
            await session.flush()

            # Generate fixtures for first round (or all rounds for some formats)
            if (
                tournament.type == TournamentType.REGULAR
                and tournament.league_format != LeagueFormat.SWISS
            ):
                # Generate all fixtures for league/swiss formats
                all_fixtures = []
                for round in rounds:
                    fixtures = await strategy.generate_fixtures(
                        tournament, round, teams, session
                    )
                    all_fixtures.extend(fixtures)
            else:
                # For knockout/swiss, only generate first round fixtures.
                # Subsequent rounts will require fixture generation.
                first_round = rounds[0]
                all_fixtures = await strategy.generate_fixtures(
                    tournament, first_round, teams, session
                )

            session.add_all(all_fixtures)

            # Update tournament
            tournament.actual_start_date = rounds[0].start_date
            tournament.updated_at = datetime.now(timezone.utc)

            session.add(tournament)
            return tournament

        except (ValidationError, GenerationError) as e:
            raise TournamentServiceError(str(e)) from e

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Tournament",
        details_extractor=_tournament_audit_details,
        entity_param="tournament",
    )
    async def start_tournament(
        self,
        tournament: Tournament,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Start a tournament"""
        if not tournament:
            raise TournamentServiceError("Tournament not provided")

        if tournament.status != TournamentState.NOT_STARTED:
            raise TournamentServiceError(
                "Tournament must be in NOT_STARTED status to begin"
            )

        # Get first round
        first_round = await self._get_round_by_number(tournament.id, 1, session)
        if not first_round:
            raise TournamentServiceError("No rounds found for tournament")

        # Update tournament state
        tournament.status = TournamentState.IN_PROGRESS
        tournament.actual_start_date = datetime.now(timezone.utc)
        tournament.updated_at = datetime.now(timezone.utc)

        # Activate first round
        first_round.status = "active"

        session.add(tournament)
        session.add(first_round)
        return tournament

    async def get_round_winners(
        self, round: Round, session: AsyncSession
    ) -> list[Team]:
        """Get winning teams from completed fixtures in a round"""
        # Get all fixtures for the round
        stmt = select(Fixture).where(Fixture.round_id == round.id)
        result = await session.execute(stmt)
        fixtures = result.scalars().all()

        # For completed/forfeited fixtures, get winners
        winners = []
        for fixture in fixtures:
            if fixture.status not in [FixtureStatus.COMPLETED, FixtureStatus.FORFEITED]:
                raise TournamentServiceError(
                    f"Not all fixtures are completed in round {round.round_number}"
                )

            winner_id = await fixture.get_winner_id(session)
            if not winner_id:
                raise TournamentServiceError(
                    f"No winner determined for completed fixture {fixture.id}"
                )

            winner = await session.get(Team, winner_id)
            winners.append(winner)

        return winners

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Tournament",
        details_extractor=_next_round_fixtures_audit_details,
        entity_param="tournament",  # Specify that 'tournament' parameter is the entity
    )
    async def generate_next_round_fixtures(
        self,
        tournament: Tournament,
        round_number: int,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> list[Fixture]:
        """Generate fixtures for the next round (for knockout tournaments)"""
        if (
            tournament.type != TournamentType.KNOCKOUT
            and tournament.league_format != LeagueFormat.SWISS
        ):
            raise TournamentServiceError(
                "Only knockout tournaments/swiss leagues generate per-round fixtures"
            )

        # Get the round
        round = await self._get_round_by_number(tournament.id, round_number, session)
        if not round:
            raise TournamentServiceError(f"Round {round_number} not found")

        # Get winners from previous round
        if round_number == 1:
            raise TournamentServiceError(
                "First round fixtures should be generated with tournament"
            )

        previous_round = await self._get_round_by_number(
            tournament.id, round_number - 1, session
        )
        winners = await self.get_round_winners(previous_round, session)

        # Generate fixtures
        strategy = get_generation_strategy(tournament)
        fixtures = await strategy.generate_fixtures(tournament, round, winners, session)

        session.add_all(fixtures)
        return fixtures

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Tournament",
        details_extractor=_tournament_audit_details,
    )
    async def complete_tournament(
        self,
        tournament: Tournament,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Marks a tournament as completed and triggers completion pipeline"""
        if tournament.status != TournamentState.IN_PROGRESS:
            raise ValueError("Can only complete an in-progress tournament")

        # Update tournament state - this will trigger the completion pipeline
        tournament = await self.change_tournament_status(
            tournament=tournament,
            new_status=TournamentState.COMPLETED,
            reason="Tournament completed",
            actor=actor,
            session=session,
        )

        tournament.actual_end_date = datetime.now(timezone.utc)
        session.add(tournament)
        return tournament

    ##############################################################################
    #                              MAP POOL FUNCS                                #
    ##############################################################################
    async def get_map_pool(
        self, tournament_id: uuid.UUID, session: AsyncSession
    ) -> Optional[TournamentMapPool]:
        """Get the map pool for a tournament"""
        stmt = (
            select(TournamentMapPool)
            .where(TournamentMapPool.tournament_id == tournament_id)
            .options(
                selectinload(TournamentMapPool.maps),
                selectinload(TournamentMapPool.team_votes),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type="TournamentMapPool",
        details_extractor=_map_pool_audit_details,
    )
    async def create_map_pool(
        self,
        tournament_id: uuid.UUID,
        map_pool_data: MapPoolCreate,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> TournamentMapPool:
        """Create a map pool for a tournament"""
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError("Tournament not found")

        if tournament.status != TournamentState.NOT_STARTED:
            raise TournamentServiceError(
                "Map pool can only be created before tournament starts"
            )

        # Create the map pool based on selection type
        if map_pool_data.selection_type == MapPoolSelectionType.ADMIN_DEFINED:
            map_pool = TournamentMapPool(
                tournament_id=tournament_id,
                selection_type=MapPoolSelectionType.ADMIN_DEFINED,
                status=MapPoolStatus.FINALIZED,
                finalized_at=datetime.now(timezone.utc),
            )
            session.add(map_pool)
            await session.flush()

            # Add maps to the pool
            for map_id in map_pool_data.map_ids:
                pool_map = MapPoolMap(pool_id=map_pool.id, map_id=map_id)
                session.add(pool_map)

        elif map_pool_data.selection_type == MapPoolSelectionType.TEAM_VOTING:
            voting_start = datetime.now(timezone.utc)
            voting_end = voting_start + timedelta(
                days=map_pool_data.voting_duration_days
            )

            map_pool = TournamentMapPool(
                tournament_id=tournament_id,
                selection_type=MapPoolSelectionType.TEAM_VOTING,
                status=MapPoolStatus.VOTING,
                voting_start=voting_start,
                voting_end=voting_end,
                maps_to_select=map_pool_data.maps_to_select,
                votes_per_team=map_pool_data.votes_per_team,
            )
            session.add(map_pool)
            await session.flush()

            # Add all maps as candidates for voting
            all_maps = await self.map_service.get_all_maps(session)
            for map in all_maps:
                if map.supported_modes.contains([tournament.game_mode]):
                    pool_map = MapPoolMap(
                        pool_id=map_pool.id, map_id=map.id, vote_count=0
                    )
                    session.add(pool_map)

        return map_pool

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="MapPoolVote",
        details_extractor=_map_vote_audit_details,
    )
    async def vote_for_maps(
        self,
        tournament_id: uuid.UUID,
        vote_request: MapPoolVoteRequest,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> MapPoolVoteResponse:
        """Vote for maps in a tournament map pool"""
        # Get map pool
        map_pool = await self.get_map_pool(tournament_id, session)
        if not map_pool:
            raise TournamentServiceError("Map pool not found")

        if map_pool.status != MapPoolStatus.VOTING:
            raise TournamentServiceError("Map pool is not open for voting")

        if datetime.now(timezone.utc) > map_pool.voting_end:
            raise TournamentServiceError("Voting period has ended")

        # Verify actor is captain of the team
        team = await self.team_service.get_team_by_id(vote_request.team_id, session)
        if not team:
            raise TournamentServiceError("Team not found")

        is_captain = await self.team_service.player_is_team_captain(
            actor, team, session
        )
        if not is_captain:
            raise TournamentServiceError("Only team captains can vote for maps")

        # Check existing votes
        stmt = select(MapPoolVote).where(
            MapPoolVote.pool_id == map_pool.id, MapPoolVote.team_id == team.id
        )
        result = await session.execute(stmt)
        existing_votes = result.scalars().all()

        if len(existing_votes) + len(vote_request.map_ids) > map_pool.votes_per_team:
            raise TournamentServiceError(
                f"Exceeds vote limit of {map_pool.votes_per_team}"
            )

        # Record votes
        for map_id in vote_request.map_ids:
            vote = MapPoolVote(pool_id=map_pool.id, team_id=team.id, map_id=map_id)
            session.add(vote)

            # Update vote count
            stmt = select(MapPoolMap).where(
                MapPoolMap.pool_id == map_pool.id, MapPoolMap.map_id == map_id
            )
            result = await session.execute(stmt)
            pool_map = result.scalar_one_or_none()
            if pool_map:
                pool_map.vote_count = (pool_map.vote_count or 0) + 1
                session.add(pool_map)

        return MapPoolVoteResponse(
            team_id=team.id,
            maps_voted=vote_request.map_ids,
            remaining_votes=map_pool.votes_per_team
            - len(existing_votes)
            - len(vote_request.map_ids),
        )

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TournamentMapPool",
        details_extractor=_map_pool_audit_details,
    )
    async def finalize_map_pool(
        self,
        tournament_id: uuid.UUID,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> TournamentMapPool:
        """Finalize a tournament map pool"""
        map_pool = await self.get_map_pool(tournament_id, session)
        if not map_pool:
            raise TournamentServiceError("Map pool not found")

        if map_pool.status != MapPoolStatus.VOTING:
            raise TournamentServiceError("Map pool is not in voting status")

        if datetime.now(timezone.utc) < map_pool.voting_end:
            raise TournamentServiceError("Voting period has not ended")

        # Get maps ordered by vote count
        stmt = (
            select(MapPoolMap)
            .where(MapPoolMap.pool_id == map_pool.id)
            .order_by(MapPoolMap.vote_count.desc())
        )
        result = await session.execute(stmt)
        all_pool_maps = result.scalars().all()

        # Keep only top N maps
        all_pool_maps[: map_pool.maps_to_select]
        unselected_maps = all_pool_maps[map_pool.maps_to_select :]

        # Remove unselected maps
        for pool_map in unselected_maps:
            await session.delete(pool_map)

        # Update status
        map_pool.status = MapPoolStatus.FINALIZED
        map_pool.finalized_at = datetime.now(timezone.utc)
        session.add(map_pool)

        return map_pool

    ##############################################################################
    #                              TOURNAMENT REGISTRATION                       #
    ##############################################################################
    def _registration_audit_details(
        self, registration: TournamentRegistration, *args
    ) -> dict:
        """Extract audit details for registration operations"""
        return {
            "registration_id": str(registration.id),
            "tournament_id": str(registration.tournament_id),
            "team_id": str(registration.team_id),
            "status": registration.status,
            "requested_at": registration.requested_at.isoformat(),
            "reviewed_at": registration.reviewed_at.isoformat()
            if registration.reviewed_at
            else None,
            "withdrawn_at": registration.withdrawn_at.isoformat()
            if registration.withdrawn_at
            else None,
        }

    async def get_registration(
        self,
        tournament_id: uuid.UUID,
        registration_id: uuid.UUID,
        session: AsyncSession,
    ):
        """Get a specific tournament registration"""
        stmt = select(TournamentRegistration).where(
            TournamentRegistration.tournament_id == tournament_id,
            TournamentRegistration.id == registration_id,
        )
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def get_registrations(
        self,
        tournament_id: uuid.UUID,
        status: Optional[RegistrationStatus],
        session: AsyncSession,
    ) -> TournamentRegistrationList:
        """Get all registrations for a tournament, optionally filtered by status"""
        stmt = select(TournamentRegistration).where(
            TournamentRegistration.tournament_id == tournament_id
        )
        if status:
            stmt = stmt.where(TournamentRegistration.status == status)

        result = (await session.execute(stmt)).scalars()
        registrations = result.all()

        # Calculate summary stats
        total_registered = len(
            [r for r in registrations if r.status == RegistrationStatus.APPROVED]
        )
        total_pending = len(
            [r for r in registrations if r.status == RegistrationStatus.PENDING]
        )

        return TournamentRegistrationList(
            total_registered=total_registered,
            total_pending=total_pending,
            registrations=registrations,
        )

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE,
        entity_type="TournamentRegistration",
        details_extractor=_registration_audit_details,
    )
    async def request_registration(
        self,
        registration: TournamentRegistrationRequest,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> TournamentRegistration:
        """Request registration in a tournament"""
        # Get tournament and team
        tournament_id = registration.tournament_id
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise RegistrationError("Tournament not found")

        team = await self.team_service.get_team_by_id(registration.team_id, session)
        if not team:
            raise RegistrationError("Team not found")

        # Validate registration is allowed
        await self._validate_registration_request(tournament, team, actor, session)

        # Create registration
        registration = TournamentRegistration(
            tournament_id=tournament_id,
            team_id=team.id,
            status=RegistrationStatus.PENDING,
            requested_by=actor.id,
            requested_at=datetime.now(timezone.utc),
            notes=registration.notes,
        )
        LOG.info("Returning new tournament registration")
        session.add(registration)
        return registration

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TournamentRegistration",
        details_extractor=_registration_audit_details,
    )
    async def review_registration(
        self,
        tournament_id: uuid.UUID,
        registration_id: uuid.UUID,
        review: RegistrationReviewRequest,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> TournamentRegistration:
        """Review a tournament registration request"""
        registration = await self.get_registration(
            tournament_id, registration_id, session
        )
        if not registration:
            raise RegistrationError("Registration not found")

        if registration.status != RegistrationStatus.PENDING:
            raise RegistrationError("Can only review pending registrations")

        # Update registration
        registration.status = review.status
        registration.reviewed_by = actor.id
        registration.reviewed_at = datetime.now(timezone.utc)
        registration.review_notes = review.notes

        session.add(registration)
        return registration

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="TournamentRegistration",
        details_extractor=_registration_audit_details,
    )
    async def withdraw_registration(
        self,
        tournament_id: uuid.UUID,
        registration_id: uuid.UUID,
        withdrawal: RegistrationWithdrawRequest,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> TournamentRegistration:
        """Withdraw from a tournament"""
        registration = await self.get_registration(
            tournament_id, registration_id, session
        )
        if not registration:
            raise RegistrationError("Registration not found")

        tournament = await self.get_tournament(tournament_id, session)

        # Verify actor is team captain
        is_captain = await self.team_service.player_is_team_captain(
            actor, registration.team, session
        )
        if not is_captain:
            raise RegistrationError("Only team captains can withdraw from tournaments")

        # Handle withdrawal based on tournament state
        if tournament.status == TournamentState.REGISTRATION_OPEN:
            # Simple withdrawal before registration closes
            registration.status = RegistrationStatus.WITHDRAWN
        elif tournament.status in [
            TournamentState.REGISTRATION_CLOSED,
            TournamentState.IN_PROGRESS,
        ]:
            # Withdrawal after registration closes - handle forfeits
            registration.status = RegistrationStatus.WITHDRAWN
            # TODO: Integration with fixture service to handle forfeits
        else:
            raise RegistrationError("Cannot withdraw in current tournament state")

        registration.withdrawn_by = actor.id
        registration.withdrawn_at = datetime.now(timezone.utc)
        registration.withdrawal_reason = withdrawal.reason

        session.add(registration)
        return registration

    async def _validate_registration_request(
        self, tournament: Tournament, team: Team, actor: Player, session: AsyncSession
    ):
        """Validate a registration request"""
        # Check tournament state
        if tournament.status != TournamentState.REGISTRATION_OPEN:
            if (
                tournament.status == TournamentState.REGISTRATION_CLOSED
                and tournament.allow_late_registration
                and datetime.now(timezone.utc) <= tournament.late_registration_end
            ):
                pass  # Allow late registration
            else:
                raise RegistrationError("Tournament registration is not open")

        # Check if team is already registered
        existing = await session.execute(
            select(TournamentRegistration).where(
                TournamentRegistration.tournament_id == tournament.id,
                TournamentRegistration.team_id == team.id,
                TournamentRegistration.status.in_(
                    [RegistrationStatus.PENDING, RegistrationStatus.APPROVED]
                ),
            )
        )
        if existing.scalar_one_or_none():
            raise RegistrationError("Team is already registered")

        # Verify actor is team captain
        is_captain = await self.team_service.player_is_team_captain(
            actor, team, session
        )
        if not is_captain:
            raise RegistrationError("Only team captains can register for tournaments")

        # Check team size requirements
        season = await tournament.awaitable_attrs.season
        roster_size = await self.team_service.get_active_roster_count(
            team, season, session
        )
        if roster_size < tournament.min_team_size:
            raise RegistrationError(
                f"Team must have at least {tournament.min_team_size} players"
            )

        # Check maximum registrations not exceeded
        current_registrations = await session.execute(
            select(TournamentRegistration).where(
                TournamentRegistration.tournament_id == tournament.id,
                TournamentRegistration.status == RegistrationStatus.APPROVED,
            )
        )
        if len(current_registrations.all()) >= tournament.max_teams:
            raise RegistrationError("Tournament has reached maximum team capacity")

    async def _get_registered_teams(
        self, tournament: Tournament, session: AsyncSession
    ) -> list[Team]:
        """Get all teams registered for the tournament"""
        # Get the registrations with teams and rosters eagerly loaded
        stmt = (
            select(TournamentRegistration)
            .join(Tournament)
            .where(TournamentRegistration.tournament_id == tournament.id)
            .where(TournamentRegistration.status == "approved")
            .options(
                selectinload(TournamentRegistration.team).selectinload(Team.rosters)
            )
        )

        result = await session.execute(stmt)
        registrations = result.scalars().all()

        # Extract teams from registrations
        teams = [reg.team for reg in registrations]

        # Load rosters for each team if not already loaded
        for team in teams:
            await session.refresh(team, ["rosters"])

        return teams

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE,
        entity_type="Tournament",
        details_extractor=_tournament_audit_details,
    )
    async def close_registration(
        self,
        tournament_id: uuid.UUID,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Close tournament registration"""
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError("Tournament not found")

        if tournament.status != TournamentState.REGISTRATION_OPEN:
            raise TournamentServiceError("Tournament registration is not open")

        # Transition to REGISTRATION_CLOSED
        tournament = await self.change_tournament_status(
            tournament=tournament,
            new_status=TournamentState.REGISTRATION_CLOSED,
            reason="Closing tournament registration",
            actor=actor,
            session=session,
        )

        return tournament

    async def _get_tournament_rounds(
        self, tournament: Tournament, session: AsyncSession
    ) -> list[Round]:
        """Get all rounds for a tournament"""
        stmt = (
            select(Round)
            .where(Round.tournament_id == tournament.id)
            .order_by(Round.round_number)
        )
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def _get_round_by_number(
        self, tournament_id: uuid.UUID, round_number: int, session: AsyncSession
    ) -> Optional[Round]:
        """Get a specific round by number"""
        stmt = select(Round).where(
            Round.tournament_id == tournament_id, Round.round_number == round_number
        )
        result = (await session.execute(stmt)).scalars()
        return result.first()

    async def _get_round_fixtures(
        self, round_id: uuid.UUID, session: AsyncSession
    ) -> list[Fixture]:
        """Get all fixtures for a round"""
        stmt = select(Fixture).where(Fixture.round_id == round_id)
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def get_fixtures_for_round(
        self, tournament_id: uuid.UUID, round_num: int, session: AsyncSession
    ) -> list[Fixture]:
        round = await self._get_round_by_number(tournament_id, round_num, session)
        if round is None:
            raise TournamentServiceError(
                f"Round '{round_num}' does not exist for tournament {tournament_id}"
            )
        return await self._get_round_fixtures(round.id, session)

    async def get_tournament_with_stats(
        self, tournament_id: uuid.UUID, session: AsyncSession
    ) -> TournamentWithStats:
        """Get a tournament with statistics"""
        # Get the tournament with eager loading
        stmt = (
            select(Tournament)
            .where(Tournament.id == tournament_id)
            .options(
                selectinload(Tournament.registrations),
                selectinload(Tournament.rounds).selectinload(Round.fixtures),
                selectinload(Tournament.fixtures),
            )
        )

        result = await session.execute(stmt)
        tournament = result.scalar_one_or_none()

        if not tournament:
            raise TournamentServiceError(f"Tournament {tournament_id} not found")

        # Load fixtures to get match stats
        fixtures = await self.get_tournament_fixtures(tournament_id, session)

        # Calculate statistics
        total_matches = len(fixtures)
        matches_completed = len(
            [f for f in fixtures if f.status == FixtureStatus.COMPLETED]
        )
        matches_remaining = len(
            [f for f in fixtures if f.status == FixtureStatus.SCHEDULED]
        )

        # Get current round number
        active_round = await self._get_active_round(tournament, session)
        current_round = active_round.round_number if active_round else None

        # Get tournament configuration
        map_pool = []
        if tournament.maps:
            map_pool = [map.id for map in tournament.maps]

        # Count active team registrations
        active_registrations = len(
            [
                reg
                for reg in tournament.registrations
                if reg.status == RegistrationStatus.APPROVED
            ]
        )

        return TournamentWithStats(
            id=tournament.id,
            name=tournament.name,
            type=tournament.type,
            state=tournament.status,
            season_id=tournament.season_id,
            max_team_size=tournament.max_team_size,
            created_at=tournament.created_at,
            updated_at=tournament.updated_at,
            total_teams=active_registrations,
            total_matches=total_matches,
            matches_completed=matches_completed,
            matches_remaining=matches_remaining,
            current_round=current_round,
            map_pool=map_pool,
            format_config=tournament.format_config or {},
        )

    async def _get_active_round(
        self, tournament: Tournament, session: AsyncSession
    ) -> Optional[Round]:
        """Get the currently active round for a tournament"""
        stmt = select(Round).where(
            Round.tournament_id == tournament.id, Round.status == "active"
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_tournament_fixtures(
        self,
        tournament_id: uuid.UUID,
        session: AsyncSession,
        status: Optional[FixtureStatus] = None,
    ) -> list[Fixture]:
        """Get all fixtures for a tournament"""
        stmt = select(Fixture).where(Fixture.tournament_id == tournament_id)
        if status:
            stmt = stmt.where(Fixture.status == status)
        stmt = stmt.order_by(Fixture.scheduled_at)
        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def _check_tournament_completion(
        self, tournament: Tournament, actor: Player, session: AsyncSession
    ) -> None:
        """Check if all rounds are completed and complete the tournament if needed"""
        # Get all rounds
        rounds = await self._get_tournament_rounds(tournament, session)

        # If all rounds are completed, complete the tournament
        if all(r.status == "completed" for r in rounds):
            LOG.info(
                f"All rounds completed for tournament {tournament.id} - completing tournament"
            )
            await self.complete_tournament(tournament, actor, session)

    async def complete_round(
        self,
        tournament_id: uuid.UUID,
        round_number: int,
        actor: Player,
        session: AsyncSession,
    ):
        """Facade method to complete a round - delegates to RoundService

        This is a facade method that doesn't need its own audit as the
        RoundService.complete_round already handles auditing.
        """
        # Get the tournament and round
        tournament = await self.get_tournament(tournament_id, session)
        if not tournament:
            raise TournamentServiceError(f"Tournament {tournament_id} not found")

        round = await self._get_round_by_number(tournament_id, round_number, session)
        if not round:
            raise TournamentServiceError(
                f"Round {round_number} not found for tournament {tournament_id}"
            )

        # Delegate to RoundService (which has its own auditing)
        try:
            await self.round_service.complete_round(round, actor, session)
        except TransitionError as e:
            # Re-raise TransitionError as TournamentServiceError for backward compatibility
            raise TournamentServiceError(str(e)) from e

        # Check if this was the final round and tournament should be completed
        await self._check_tournament_completion(tournament, actor, session)


def create_tournament_service(
    team_svc: Optional[TeamService] = None,
    match_svc: Optional[MatchService] = None,
    round_svc: Optional[RoundService] = None,
    audit_svc: Optional[AuditService] = None,
    status_svc: Optional[StatusTransitionService] = None,
):
    team_service = team_svc or TeamService()
    match_service = match_svc or MatchService()
    round_service = round_svc or RoundService()
    audit_service = audit_svc or AuditService()
    status_service = status_svc or StatusTransitionService()
    return TournamentService(
        team_service, match_service, round_service, audit_service, status_service
    )
