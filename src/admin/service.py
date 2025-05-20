import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from sqlalchemy import and_
from sqlalchemy.orm import selectinload
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from admin.schemas import (
    DisputeResolution, 
    DisputeResolutionType,
    ModerationActionRequest,
    PlayerEloAdjustment,
    RosterChangeRequest,
    TeamDisbandRequest,
    TournamentConfigUpdate,
    TournamentStatusForce,
)
from audit.context import AuditContext
from audit.schemas import AuditEventType
from audit.service import AuditService
from auth.models import Player, Role
from auth.schemas import PlayerRoleAssign, PlayerStatus, PlayerVerificationUpdate
from auth.service.auth import AuthService, create_auth_service
from competitions.base_schemas import LeagueFormat
from status.manager.round import RoundStatus
from competitions.models.fixtures import Fixture
from competitions.models.rounds import Round
from competitions.models.tournaments import (
    Tournament, 
    TournamentRegistration, 
    TournamentState,
    TournamentType,
)
from matches.models import ConfirmationStatus, DisputeStatus, MatchDispute, Result
from matches.schemas import AdminResultOverride
from moderation.models import Ban, BanStatus, ModerationAction, ModerationActionType
from moderation.schemas import BanCreate, ModerationActionCreate
from status.manager.dispute import initialize_dispute_status_manager
from status.manager.result import initialize_result_status_manager
from status.pipeline import TransitionPipeline
from status.service import StatusTransitionService, create_enhanced_status_transition_service
from teams.base_schemas import TeamCaptainStatus, TeamStatus
from teams.models import Roster, RosterStatus, Team, TeamCaptain


class AdminServiceError(Exception):
    """Base exception for admin service errors"""
    pass


class AdminService:
    def __init__(
        self,
        auth_service: AuthService,
        status_service: StatusTransitionService,
    ):
        self.auth_service = auth_service
        self.status_transition_service = status_service

        # Initialize result and dispute status managers
        result_manager = initialize_result_status_manager()
        dispute_manager = initialize_dispute_status_manager()

        # Register managers with status transition service
        self.status_transition_service.register_transition_manager("Result", result_manager)
        self.status_transition_service.register_transition_manager("MatchDispute", dispute_manager)

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Player"
    )
    async def verify_player(
        self,
        player_id: uuid.UUID,
        verification: PlayerVerificationUpdate,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Player:
        """Process a player verification request"""
        player = await session.get(Player, player_id)
        if not player:
            raise ValueError("Player not found")

        entity_metadata = {
            "verification_date": verification.verification_date.isoformat(),
            "verified_by": str(actor.id),
            "verification_notes": verification.admin_notes,
        }

        # Log the evidence used if submitted
        if player.verification_evidence:
            entity_metadata["verification_evidence"] = player.verification_evidence

        # Use status transition service to trigger appropriate pipeline
        await self.status_transition_service.transition_status(
            entity=player,
            new_status=verification.status,
            reason=verification.admin_notes,
            actor=actor,
            entity_metadata=entity_metadata,
            session=session,
            audit_context=audit_context,
        )

        return player

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE, entity_type="Ban"
    )
    async def ban_player(
        self,
        player_id: uuid.UUID,
        ban_data: BanCreate,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Ban:
        """Ban a player and trigger the ban pipeline"""
        player = await session.get(Player, player_id)
        if not player:
            raise ValueError("Player not found")

        # Create ban record first
        ban = Ban(
            player_id=player.id,
            scope=ban_data.scope,
            scope_id=ban_data.scope_id,
            reason=ban_data.reason,
            evidence=ban_data.evidence,
            status=BanStatus.ACTIVE,
            start_date=datetime.now(timezone.utc),
            end_date=ban_data.end_date,
            issued_by=actor.id,
        )
        session.add(ban)
        await session.flush()  # Get the ban ID

        # Prepare additional context for pipeline
        ban_context = {
            "ban_id": str(ban.id),
            "ban_scope": ban_data.scope,
            "ban_end_date": ban_data.end_date.isoformat()
            if ban_data.end_date
            else None,
            # Additional context for pipeline steps
        }

        # Use status transition service to trigger ban pipeline
        await self.status_transition_service.transition_status(
            entity=player,
            new_status=PlayerStatus.BANNED,
            reason=ban_data.reason,
            actor=actor,
            entity_metadata=ban_context,
            session=session,
            audit_context=audit_context,
        )

        return ban

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Ban"
    )
    async def revoke_ban(
        self,
        ban_id: uuid.UUID,
        reason: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Ban:
        """Revoke a ban and restore player status"""
        ban = await session.get(Ban, ban_id)
        if not ban:
            raise ValueError("Ban not found")

        if ban.status != BanStatus.ACTIVE:
            raise ValueError("Ban is not active")

        # Update ban status
        ban.status = BanStatus.REVOKED
        ban.revoked_by = actor.id
        ban.revoke_reason = reason
        session.add(ban)
        await session.flush()

        # Check if there are any other active bans
        stmt = select(Ban).where(
            Ban.player_id == ban.player_id, Ban.status == BanStatus.ACTIVE
        )
        active_bans = (await session.execute(stmt)).scalars().all()

        # If no other active bans, restore player
        if not active_bans:
            player = await session.get(Player, ban.player_id)
            if player and player.status == PlayerStatus.BANNED:
                # Prepare context for pipeline
                unban_context = {
                    "revoked_ban_id": str(ban.id),
                    "revoke_reason": reason,
                    "auth_service": self.auth_service,
                }

                # Use status transition service to trigger unban pipeline
                await self.status_transition_service.transition_status(
                    entity=player,
                    new_status=PlayerStatus.ACTIVE,
                    reason=f"Ban {ban_id} revoked: {reason}",
                    actor=actor,
                    entity_metadata=unban_context,
                    session=session,
                    audit_context=audit_context,
                )

        return ban

    async def get_player_bans(
        self, player_id: uuid.UUID, include_inactive: bool, session: AsyncSession
    ) -> list[Ban]:
        """Get a player's ban history"""
        stmt = select(Ban).where(Ban.player_id == player_id)
        if not include_inactive:
            stmt = stmt.where(Ban.status == BanStatus.ACTIVE)
        stmt = stmt.order_by(desc(Ban.created_at))

        result = (await session.execute(stmt)).scalars()
        return result.all()

    async def assign_role(
        self,
        player_id: uuid.UUID,
        role_data: PlayerRoleAssign,
        actor: Player,
        session: AsyncSession,
    ) -> Player:
        """Assign a role to a player"""
        player = await self.auth_service.get_player_by_id(player_id, session)
        if not player:
            raise AdminServiceError("Player not found")

        role = await session.get(Role, role_data.role_id)
        if not role:
            raise AdminServiceError("Role not found")

        # Use auth service to handle role assignment with proper scoping
        await self.auth_service.assign_role(
            player=player,
            role=role,
            scope_type=role_data.scope_type,
            scope_id=role_data.scope_id,
            actor=actor,
            session=session,
        )

        return player

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Result"
    )
    async def override_match_result(
        self,
        result_id: uuid.UUID,
        override_data: AdminResultOverride,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Result:
        """Override a match result with admin authority"""
        result = await session.get(Result, result_id)
        if not result:
            raise AdminServiceError("Result not found")

        # Use status transition to change to admin override
        context = {
            "team_1_score": override_data.team_1_score,
            "team_2_score": override_data.team_2_score,
            "override_reason": override_data.reason,
        }

        await self.status_transition_service.transition_status(
            entity=result,
            new_status=ConfirmationStatus.ADMIN_OVERRIDE,
            reason=override_data.reason,
            actor=actor,
            entity_metadata=context,
            session=session,
            audit_context=audit_context,
        )

        return result

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="MatchDispute"
    )
    async def resolve_dispute(
        self,
        dispute_id: uuid.UUID,
        resolution: DisputeResolution,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> MatchDispute:
        """Resolve a match dispute using status transitions"""
        dispute = await session.get(MatchDispute, dispute_id)
        if not dispute:
            raise AdminServiceError("Dispute not found")

        # Determine the target status based on resolution type
        if resolution.resolution_type in [
            DisputeResolutionType.ACCEPT_RESULT,
            DisputeResolutionType.OVERRIDE_RESULT,
            DisputeResolutionType.VOID_MATCH,
        ]:
            target_status = DisputeStatus.RESOLVED
        else:
            # REPLAY_MATCH would go to a different status
            target_status = DisputeStatus.RESOLVED  # For now

        # Prepare context for the transition
        context = {
            "resolution_type": resolution.resolution_type.value,
            "resolution_reason": resolution.reason,
            "team_1_score": resolution.team_1_score,
            "team_2_score": resolution.team_2_score,
            "evidence_urls": resolution.evidence_urls,
        }

        await self.status_transition_service.transition_status(
            entity=dispute,
            new_status=target_status,
            reason=resolution.reason,
            actor=actor,
            entity_metadata=context,
            session=session,
            audit_context=audit_context,
        )

        return dispute

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Tournament"
    )
    async def update_tournament_config(
        self,
        tournament_id: uuid.UUID,
        update_data: TournamentConfigUpdate,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Update tournament configuration"""
        tournament = await session.get(Tournament, tournament_id)
        if not tournament:
            raise AdminServiceError("Tournament not found")

        # Store original configuration for audit purposes
        original_config = {
            "name": tournament.name,
            "max_teams": tournament.max_teams,
            "min_teams": tournament.min_teams,
            "max_team_size": tournament.max_team_size,
            "min_team_size": tournament.min_team_size,
            "registration_start": tournament.registration_start,
            "registration_end": tournament.registration_end,
            "scheduled_start": tournament.scheduled_start,
            "scheduled_end_date": tournament.scheduled_end_date,
            "rules": tournament.rules,
        }

        # Update tournament configuration
        if update_data.name is not None:
            tournament.name = update_data.name
        if update_data.max_teams is not None:
            tournament.max_teams = update_data.max_teams
        if update_data.min_teams is not None:
            tournament.min_teams = update_data.min_teams
        if update_data.max_team_size is not None:
            tournament.max_team_size = update_data.max_team_size
        if update_data.min_team_size is not None:
            tournament.min_team_size = update_data.min_team_size
        if update_data.registration_start is not None:
            tournament.registration_start = update_data.registration_start
        if update_data.registration_end is not None:
            tournament.registration_end = update_data.registration_end
        if update_data.scheduled_start is not None:
            tournament.scheduled_start = update_data.scheduled_start
        if update_data.scheduled_end is not None:
            tournament.scheduled_end_date = update_data.scheduled_end
        if update_data.rules is not None:
            tournament.rules = update_data.rules

        # Update format configuration if provided
        if update_data.format_config is not None:
            if tournament.format == LeagueFormat.SWISS:
                if update_data.format_config.get("num_rounds") is not None:
                    tournament.swiss_rounds = update_data.format_config.get("num_rounds")
            elif tournament.format == LeagueFormat.KNOCKOUT:
                if update_data.format_config.get("double_elimination") is not None:
                    tournament.double_elimination = update_data.format_config.get("double_elimination")
                if update_data.format_config.get("third_place") is not None:
                    tournament.third_place_match = update_data.format_config.get("third_place")

        session.add(tournament)
        await session.flush()

        return tournament

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Tournament"
    )
    async def force_tournament_status(
        self,
        tournament_id: uuid.UUID,
        new_status: str,
        reason: str,
        skip_validations: bool = False,
        actor: Player = None,
        session: AsyncSession = None,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Tournament:
        """Force a tournament status change"""
        tournament = await session.get(Tournament, tournament_id)
        if not tournament:
            raise AdminServiceError("Tournament not found")

        try:
            # Convert string to enum state
            target_status = TournamentState(new_status)
        except ValueError:
            raise AdminServiceError(f"Invalid tournament status: {new_status}")

        # Use status transition service to handle the change
        context = {
            "skip_validations": skip_validations,
            "admin_forced": True,
        }

        await self.status_transition_service.transition_status(
            entity=tournament,
            new_status=target_status,
            reason=reason,
            actor=actor,
            entity_metadata=context,
            session=session,
            audit_context=audit_context,
        )

        return tournament

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE, entity_type="Round"
    )
    async def generate_tournament_round(
        self,
        tournament_id: uuid.UUID,
        round_number: int,
        round_type: Optional[str],
        force_pairings: Optional[List[Dict[str, Any]]] = None,
        actor: Player = None,
        session: AsyncSession = None,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Round:
        """Manually generate a tournament round"""
        from services.tournament import tournament_service

        tournament = await session.get(Tournament, tournament_id)
        if not tournament:
            raise AdminServiceError("Tournament not found")

        # Check if tournament is in a valid state
        if tournament.state not in [TournamentState.IN_PROGRESS, TournamentState.NOT_STARTED]:
            raise AdminServiceError(f"Tournament is in {tournament.state} state. Cannot generate rounds.")

        # Check if the round already exists
        existing_round = await tournament_service._get_round_by_number(tournament_id, round_number, session)
        if existing_round:
            raise AdminServiceError(f"Round {round_number} already exists for this tournament.")

        # Create the round
        round_type_enum = None
        if round_type:
            # Convert string to appropriate enum based on tournament format
            if tournament.format == LeagueFormat.SWISS:
                # For Swiss, round types are Swiss1, Swiss2, etc.
                round_type_enum = f"Swiss{round_number}"
            elif tournament.format == LeagueFormat.KNOCKOUT:
                # For Knockout, the validation needs more complexity
                if round_type not in ["RoundOf16", "QuarterFinal", "SemiFinal", "Final", "ThirdPlace"]:
                    raise AdminServiceError(f"Invalid round type '{round_type}' for knockout format")
                round_type_enum = round_type

        # Create a new round
        new_round = Round(
            tournament_id=tournament_id,
            round_number=round_number,
            round_type=round_type_enum,
            status=RoundStatus.PENDING,
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=7),  # Default 7 days
            created_by=actor.id,
        )
        session.add(new_round)
        await session.flush()

        # If we have forced pairings, create fixtures based on those
        if force_pairings and len(force_pairings) > 0:
            for pairing in force_pairings:
                team1_id = pairing.get("team1_id")
                team2_id = pairing.get("team2_id")

                if not team1_id or not team2_id:
                    continue

                # Create fixture with the forced pairing
                fixture = Fixture(
                    tournament_id=tournament_id,
                    round_id=new_round.id,
                    team_1=uuid.UUID(team1_id),
                    team_2=uuid.UUID(team2_id),
                    status="scheduled",
                    scheduled_at=new_round.start_date + timedelta(days=1),
                    match_format="bo3",  # Default
                    created_by=actor.id,
                )
                session.add(fixture)

            await session.flush()
        else:
            # Use the tournament service to generate fixtures automatically
            await tournament_service._generate_fixtures_for_round(tournament, new_round, session)

        return new_round

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Team"
    )
    async def disband_team(
        self,
        team_id: uuid.UUID,
        disband_data: TeamDisbandRequest,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Team:
        """Force disband a team"""
        from services.team import team_service

        team = await session.get(Team, team_id)
        if not team:
            raise AdminServiceError("Team not found")

        # Use status transition service to handle disband
        context = {
            "ban_captain": disband_data.ban_captain,
            "remove_from_tournaments": disband_data.remove_from_tournaments,
            "admin_forced": True
        }

        await self.status_transition_service.transition_status(
            entity=team,
            new_status=TeamStatus.DISBANDED,
            reason=disband_data.reason,
            actor=actor,
            entity_metadata=context,
            session=session,
            audit_context=audit_context,
        )

        return team

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Team"
    )
    async def modify_team_roster(
        self,
        team_id: uuid.UUID,
        roster_change: RosterChangeRequest,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Union[TeamCaptain, Roster, None]:
        """Modify team roster as admin"""
        from services.captain import captain_service
        from services.roster import roster_service
        from services.team import team_service

        team = await session.get(Team, team_id)
        if not team:
            raise AdminServiceError("Team not found")

        player = await session.get(Player, roster_change.player_id)
        if not player:
            raise AdminServiceError("Player not found")

        # Check which action to perform
        if roster_change.action == "add":
            # Check if player already on team
            existing_roster = await roster_service.get_player_roster(player.id, team.id, None, session)
            if existing_roster:
                raise AdminServiceError("Player is already on this team")

            # Get active season
            from services.season import season_service
            active_season = await season_service.get_active_season(session)
            if not active_season:
                raise AdminServiceError("No active season found")

            # Add player to roster
            return await roster_service.add_player_to_team(
                team=team,
                player=player,
                season=active_season,
                actor=actor,
                session=session,
            )

        elif roster_change.action == "remove":
            # Check if player is on team
            existing_roster = await roster_service.get_player_roster(player.id, team.id, None, session)
            if not existing_roster:
                raise AdminServiceError("Player is not on this team")

            # Remove player from roster
            await roster_service.remove_player_from_team(
                roster=existing_roster,
                reason=roster_change.reason,
                actor=actor,
                session=session,
            )
            return existing_roster

        elif roster_change.action == "promote_captain":
            # Promote to captain
            return await captain_service.add_captain(
                team=team,
                player=player,
                actor=actor,
                session=session,
            )

        elif roster_change.action == "demote_captain":
            # Check if player is a captain
            stmt = select(TeamCaptain).where(
                TeamCaptain.team_id == team.id,
                TeamCaptain.player_id == player.id,
                TeamCaptain.status == TeamCaptainStatus.ACTIVE,
            )
            result = (await session.execute(stmt)).scalars().first()
            if not result:
                raise AdminServiceError("Player is not an active captain of this team")

            # Demote from captain
            return await captain_service.remove_captain(
                team_captain=result,
                reason=roster_change.reason,
                actor=actor,
                session=session,
            )

        else:
            raise AdminServiceError(f"Invalid action: {roster_change.action}")

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Player"
    )
    async def adjust_player_elo(
        self,
        player_id: uuid.UUID,
        elo_adjustment: PlayerEloAdjustment,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> Player:
        """Adjust a player's ELO rating"""
        player = await session.get(Player, player_id)
        if not player:
            raise AdminServiceError("Player not found")

        # Calculate new ELO
        current_elo = player.current_elo or 1500  # Default starting ELO

        if elo_adjustment.adjustment_type == "set":
            new_elo = elo_adjustment.new_elo
        elif elo_adjustment.adjustment_type == "add":
            new_elo = current_elo + elo_adjustment.new_elo
        elif elo_adjustment.adjustment_type == "subtract":
            new_elo = current_elo - elo_adjustment.new_elo
            if new_elo < 0:
                new_elo = 0  # Don't allow negative ELO
        else:
            raise AdminServiceError(f"Invalid adjustment type: {elo_adjustment.adjustment_type}")

        # Record previous highest ELO if this is a new high
        if not player.highest_elo or new_elo > player.highest_elo:
            player.highest_elo = new_elo

        # Update the player
        player.current_elo = new_elo
        player.updated_at = datetime.now(timezone.utc)
        session.add(player)
        await session.flush()

        return player

    @AuditService.audited_transaction(
        action_type=AuditEventType.UPDATE, entity_type="Player"
    )
    async def force_remove_from_teams(
        self,
        player_id: uuid.UUID,
        reason: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> None:
        """Force remove a player from all teams"""
        from services.roster import roster_service
        from services.captain import captain_service
        from services.season import season_service

        player = await session.get(Player, player_id)
        if not player:
            raise AdminServiceError("Player not found")

        # Get active season
        active_season = await season_service.get_active_season(session)
        if not active_season:
            raise AdminServiceError("No active season found")

        # Get all active team rosters for this player
        stmt = select(Roster).where(
            Roster.player_id == player_id,
            Roster.season_id == active_season.id,
            Roster.status == RosterStatus.ACTIVE
        ).options(selectinload(Roster.team))

        result = (await session.execute(stmt)).scalars().all()

        # Remove from each team's roster
        for roster in result:
            await roster_service.remove_player_from_team(
                roster=roster,
                reason=f"Admin forced removal: {reason}",
                actor=actor,
                session=session,
            )

        # Also remove any captain positions
        stmt = select(TeamCaptain).where(
            TeamCaptain.player_id == player_id,
            TeamCaptain.status == TeamCaptainStatus.ACTIVE
        )

        captaincies = (await session.execute(stmt)).scalars().all()

        for captaincy in captaincies:
            await captain_service.remove_captain(
                team_captain=captaincy,
                reason=f"Admin forced removal: {reason}",
                actor=actor,
                session=session,
            )

    @AuditService.audited_transaction(
        action_type=AuditEventType.CREATE, entity_type="ModerationAction"
    )
    async def apply_moderation_action(
        self,
        player_id: uuid.UUID,
        action: ModerationActionRequest,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,  # noqa: ARG002
    ) -> ModerationAction:
        """Apply a moderation action to a player"""
        player = await session.get(Player, player_id)
        if not player:
            raise AdminServiceError("Player not found")

        # Create duration if specified
        end_date = None
        if action.duration_days:
            end_date = datetime.now(timezone.utc) + timedelta(days=action.duration_days)

        # Map action type to enum
        try:
            action_type = ModerationActionType(action.action_type)
        except ValueError:
            raise AdminServiceError(f"Invalid action type: {action.action_type}")

        # Create action record
        moderation_action = ModerationAction(
            player_id=player.id,
            action_type=action_type,
            reason=action.reason,
            scope=action.scope,
            scope_id=action.scope_id if action.scope_id else None,
            start_date=datetime.now(timezone.utc),
            end_date=end_date,
            issued_by=actor.id,
            active=True
        )

        session.add(moderation_action)
        await session.flush()

        # If this is a ban, apply the ban logic
        if action.action_type == "ban":
            ban_data = BanCreate(
                scope=action.scope,
                scope_id=action.scope_id,
                reason=action.reason,
                evidence=[],
                end_date=end_date
            )

            await self.ban_player(
                player_id=player.id,
                ban_data=ban_data,
                actor=actor,
                session=session
            )

        # If it's a suspension, mark player as suspended
        if action.action_type == "suspension":
            await self.status_transition_service.transition_status(
                entity=player,
                new_status=PlayerStatus.SUSPENDED,
                reason=action.reason,
                actor=actor,
                entity_metadata={
                    "suspension_id": str(moderation_action.id),
                    "end_date": end_date.isoformat() if end_date else None,
                },
                session=session,
                audit_context=audit_context,
            )

        return moderation_action

    async def get_all_players(
        self,
        skip: int,
        limit: int,
        actor: Player,  # noqa: ARG002
        session: AsyncSession,
    ) -> list[Player]:
        """Get all players with pagination"""
        stmt = select(Player).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()


def create_admin_service(
    auth_svc: Optional[AuthService] = None,
    status_transition_svc: Optional[StatusTransitionService] = None,
) -> AdminService:
    """Create and configure AdminService with its dependencies"""
    auth_service = auth_svc or create_auth_service()
    status_transition_service = (
        status_transition_svc or create_enhanced_status_transition_service()
    )
    return AdminService(
        auth_service=auth_service,
        status_service=status_transition_service,
    )