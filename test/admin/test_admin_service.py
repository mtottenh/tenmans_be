"""Test suite for AdminService business logic"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
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
from admin.service import AdminService, AdminServiceError, create_admin_service
from auth.models import Player, Role
from auth.schemas import PlayerStatus, PlayerVerificationUpdate, ScopeType
from auth.service.permission import PermissionScope
from competitions.base_schemas import LeagueFormat
from status.manager.round import RoundStatus
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.tournaments import Tournament, TournamentState
from matches.models import ConfirmationStatus, DisputeStatus, MatchDispute, Result
from matches.schemas import AdminResultOverride
from moderation.models import Ban, BanStatus, ModerationActionType
from moderation.schemas import BanCreate
from status.service import create_enhanced_status_transition_service
from teams.base_schemas import TeamCaptainStatus, TeamStatus
from teams.models import RosterStatus, Team


@pytest_asyncio.fixture
async def admin_service(
    session: AsyncSession,
    admin_user: Player,
    test_roles: dict[str, Role],
    system_user: Player,
) -> AdminService:
    """Create AdminService with properly initialized dependencies."""
    from auth.service.auth import create_auth_service
    auth_service = create_auth_service()
    status_service = create_enhanced_status_transition_service()
    return create_admin_service(
        auth_svc=auth_service,
        status_transition_svc=status_service,
    )


@pytest_asyncio.fixture
async def test_tournament(
    session: AsyncSession,
    test_season: dict,
    admin_user: Player,
) -> Tournament:
    """Create a test tournament for testing."""
    tournament = Tournament(
        name="Test Tournament",
        format=LeagueFormat.SWISS,
        season_id=test_season.id,
        state=TournamentState.REGISTRATION_OPEN,
        registration_start=datetime.now(timezone.utc) - timedelta(days=1),
        registration_end=datetime.now(timezone.utc) + timedelta(days=7),
        scheduled_start=datetime.now(timezone.utc) + timedelta(days=14),
        scheduled_end_date=datetime.now(timezone.utc) + timedelta(days=60),
        swiss_rounds=3,
        max_teams=16,
        min_teams=4,
        max_team_size=7,
        min_team_size=5,
        created_by=admin_user.id,
    )
    session.add(tournament)
    await session.commit()
    await session.refresh(tournament)
    return tournament


@pytest_asyncio.fixture
async def test_team(
    session: AsyncSession,
    admin_user: Player,
    test_season: dict,
) -> Team:
    """Create a test team for testing."""
    from services.team import team_service

    # Create team
    team = await team_service.create_team(
        name="Test Team",
        captain=admin_user,
        actor=admin_user,
        logo_path=None,
        session=session,
    )

    return team


@pytest_asyncio.fixture
async def test_result(
    session: AsyncSession,
    test_tournament: Tournament,
    test_team: Team,
    admin_user: Player,
) -> Result:
    """Create a test match result."""
    # Create fixture
    fixture = Fixture(
        tournament_id=test_tournament.id,
        team_1=test_team.id,
        team_2=uuid.uuid4(),  # Another team
        status=FixtureStatus.SCHEDULED,
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        created_by=admin_user.id,
    )
    session.add(fixture)
    await session.flush()

    # Create result
    result = Result(
        fixture_id=fixture.id,
        map_id=uuid.uuid4(),
        map_number=1,
        team_1_score=16,
        team_2_score=14,
        team_1_side_first="CT",
        confirmation_status=ConfirmationStatus.PENDING,
        submitted_by=admin_user.id,
    )
    session.add(result)
    await session.commit()
    await session.refresh(result)
    return result


@pytest_asyncio.fixture
async def test_dispute(
    session: AsyncSession,
    test_result: Result,
    admin_user: Player,
) -> MatchDispute:
    """Create a test match dispute."""
    dispute = MatchDispute(
        result_id=test_result.id,
        disputed_by=admin_user.id,
        reason="Score is incorrect",
        status=DisputeStatus.PENDING,
    )
    session.add(dispute)
    await session.commit()
    await session.refresh(dispute)
    return dispute


class TestAdminService:
    """Test suite for AdminService."""

    @pytest.mark.asyncio
    async def test_override_match_result(
        self,
        admin_service: AdminService,
        test_result: Result,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test overriding a match result as admin."""
        # Arrange
        override_data = AdminResultOverride(
            result_id=test_result.id,
            team_1_score=15,
            team_2_score=15,
            reason="Admin override due to incorrect score",
        )

        # Act
        updated_result = await admin_service.override_match_result(
            result_id=test_result.id,
            override_data=override_data,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert updated_result.confirmation_status == ConfirmationStatus.ADMIN_OVERRIDE
        assert updated_result.team_1_score == 15
        assert updated_result.team_2_score == 15
        assert updated_result.admin_override is True
        assert updated_result.admin_override_by == admin_user.id
        assert updated_result.admin_override_reason == override_data.reason

    @pytest.mark.asyncio
    async def test_resolve_dispute(
        self,
        admin_service: AdminService,
        test_dispute: MatchDispute,
        test_result: Result,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test resolving a match dispute."""
        # Arrange
        resolution = DisputeResolution(
            resolution_type=DisputeResolutionType.OVERRIDE_RESULT,
            reason="Admin resolved the dispute",
            team_1_score=14,
            team_2_score=16,
        )

        # Act
        dispute = await admin_service.resolve_dispute(
            dispute_id=test_dispute.id,
            resolution=resolution,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert dispute.status == DisputeStatus.RESOLVED
        assert dispute.resolved is True
        assert dispute.resolved_by == admin_user.id

        # Refresh result to check its status
        await session.refresh(test_result)
        assert test_result.confirmation_status == ConfirmationStatus.ADMIN_OVERRIDE

    @pytest.mark.asyncio
    async def test_update_tournament_config(
        self,
        admin_service: AdminService,
        test_tournament: Tournament,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test updating tournament configuration."""
        # Arrange
        update_data = TournamentConfigUpdate(
            name="Updated Tournament",
            max_teams=24,
            min_teams=8,
            max_team_size=6,
            format_config={"num_rounds": 5},
        )

        # Act
        updated_tournament = await admin_service.update_tournament_config(
            tournament_id=test_tournament.id,
            update_data=update_data,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert updated_tournament.name == "Updated Tournament"
        assert updated_tournament.max_teams == 24
        assert updated_tournament.min_teams == 8
        assert updated_tournament.max_team_size == 6
        assert updated_tournament.swiss_rounds == 5

    @pytest.mark.asyncio
    async def test_force_tournament_status(
        self,
        admin_service: AdminService,
        test_tournament: Tournament,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test forcing a tournament status change."""
        # Arrange
        status_data = TournamentStatusForce(
            new_status=TournamentState.REGISTRATION_CLOSED,
            reason="Admin forced status change",
            skip_validations=True,
        )

        # Act
        updated_tournament = await admin_service.force_tournament_status(
            tournament_id=test_tournament.id,
            new_status=status_data.new_status,
            reason=status_data.reason,
            skip_validations=status_data.skip_validations,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert updated_tournament.state == TournamentState.REGISTRATION_CLOSED

    @pytest.mark.asyncio
    async def test_generate_tournament_round(
        self,
        admin_service: AdminService,
        test_tournament: Tournament,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test manually generating a tournament round."""
        # Arrange - First change tournament state to IN_PROGRESS
        test_tournament.state = TournamentState.IN_PROGRESS
        session.add(test_tournament)
        await session.commit()
        await session.refresh(test_tournament)

        # Act
        new_round = await admin_service.generate_tournament_round(
            tournament_id=test_tournament.id,
            round_number=1,
            round_type=None,
            force_pairings=None,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert new_round.tournament_id == test_tournament.id
        assert new_round.round_number == 1
        assert new_round.status == RoundStatus.PENDING

    @pytest.mark.asyncio
    async def test_disband_team(
        self,
        admin_service: AdminService,
        test_team: Team,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test disbanding a team."""
        # Arrange
        disband_data = TeamDisbandRequest(
            reason="Admin forced team disband",
            ban_captain=False,
            remove_from_tournaments=True,
        )

        # Act
        disbanded_team = await admin_service.disband_team(
            team_id=test_team.id,
            disband_data=disband_data,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert disbanded_team.status == TeamStatus.DISBANDED

    @pytest.mark.asyncio
    async def test_modify_team_roster_add_player(
        self,
        admin_service: AdminService,
        test_team: Team,
        test_players: dict[str, Player],
        test_season: dict,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test adding a player to team roster."""
        # Arrange
        player = test_players["another_user"]
        roster_change = RosterChangeRequest(
            player_id=str(player.id),
            action="add",
            reason="Admin added player to team",
        )

        # Act
        result = await admin_service.modify_team_roster(
            team_id=test_team.id,
            roster_change=roster_change,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert result is not None
        assert result.player_id == player.id
        assert result.team_id == test_team.id
        assert result.status == RosterStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_modify_team_roster_remove_player(
        self,
        admin_service: AdminService,
        test_team: Team,
        test_players: dict[str, Player],
        test_season: dict,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test removing a player from team roster."""
        # Arrange - First add a player
        from services.roster import roster_service

        player = test_players["another_user"]
        await roster_service.add_player_to_team(
            team=test_team,
            player=player,
            season=test_season,
            actor=admin_user,
            session=session,
        )

        # Now remove
        roster_change = RosterChangeRequest(
            player_id=str(player.id),
            action="remove",
            reason="Admin removed player from team",
        )

        # Act
        result = await admin_service.modify_team_roster(
            team_id=test_team.id,
            roster_change=roster_change,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert result is not None
        assert result.player_id == player.id
        assert result.team_id == test_team.id
        assert result.status == RosterStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_modify_team_roster_promote_captain(
        self,
        admin_service: AdminService,
        test_team: Team,
        test_players: dict[str, Player],
        test_season: dict,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test promoting a player to captain."""
        # Arrange - First add a player
        from services.roster import roster_service

        player = test_players["another_user"]
        await roster_service.add_player_to_team(
            team=test_team,
            player=player,
            season=test_season,
            actor=admin_user,
            session=session,
        )

        # Now promote to captain
        roster_change = RosterChangeRequest(
            player_id=str(player.id),
            action="promote_captain",
            reason="Admin promoted player to captain",
        )

        # Act
        result = await admin_service.modify_team_roster(
            team_id=test_team.id,
            roster_change=roster_change,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert result is not None
        assert result.player_id == player.id
        assert result.team_id == test_team.id
        assert result.status == TeamCaptainStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_adjust_player_elo(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test adjusting player ELO."""
        # Arrange
        player = test_players["regular_user"]
        original_elo = player.current_elo or 1500

        elo_adjustment = PlayerEloAdjustment(
            new_elo=100,
            adjustment_type="add",
            reason="Admin adjusted ELO",
        )

        # Act
        updated_player = await admin_service.adjust_player_elo(
            player_id=player.id,
            elo_adjustment=elo_adjustment,
            actor=admin_user,
            session=session,
        )

        # Assert
        expected_elo = original_elo + 100
        assert updated_player.current_elo == expected_elo
        if not player.highest_elo or expected_elo > player.highest_elo:
            assert updated_player.highest_elo == expected_elo

    @pytest.mark.asyncio
    async def test_apply_moderation_action_warning(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test applying a warning moderation action."""
        # Arrange

        player = test_players["regular_user"]
        action = ModerationActionRequest(
            action_type="warning",
            reason="Rule violation",
            scope="global",
        )

        # Act
        moderation_action = await admin_service.apply_moderation_action(
            player_id=player.id,
            action=action,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert moderation_action.player_id == player.id
        assert moderation_action.action_type == ModerationActionType.WARNING
        assert moderation_action.reason == "Rule violation"
        assert moderation_action.active is True

    @pytest.mark.asyncio
    async def test_apply_moderation_action_ban(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test applying a ban moderation action."""
        # Arrange

        player = test_players["regular_user"]
        action = ModerationActionRequest(
            action_type="ban",
            duration_days=30,
            reason="Severe rule violation",
            scope="global",
        )

        # Act
        moderation_action = await admin_service.apply_moderation_action(
            player_id=player.id,
            action=action,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert moderation_action.player_id == player.id
        assert moderation_action.action_type == ModerationActionType.BAN
        assert moderation_action.reason == "Severe rule violation"
        assert moderation_action.active is True

        # Check if player is now banned
        await session.refresh(player)
        assert player.status == PlayerStatus.BANNED

    @pytest.mark.asyncio
    async def test_verify_player(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test verifying a player."""
        # Arrange

        player = test_players["regular_user"]
        player.status = PlayerStatus.PENDING_VERIFICATION
        session.add(player)
        await session.commit()

        verification = PlayerVerificationUpdate(
            status=PlayerStatus.VERIFIED,
            verification_date=datetime.now(timezone.utc),
            admin_notes="Identity verified",
        )

        # Act
        verified_player = await admin_service.verify_player(
            player_id=player.id,
            verification=verification,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert verified_player.status == PlayerStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_ban_player_not_found(
        self,
        admin_service: AdminService,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test ban fails for non-existent player."""
        # Arrange

        non_existent_id = uuid.uuid4()
        ban_data = BanCreate(
            scope="global",
            scope_id=None,
            reason="Violation of rules",
            evidence=["evidence1.jpg"],
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Player not found"):
            await admin_service.ban_player(
                player_id=non_existent_id,
                ban_data=ban_data,
                actor=admin_user,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_revoke_ban(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test revoking a player ban."""
        # Arrange - First create a ban
        player = test_players["regular_user"]

        # Create ban
        ban = Ban(
            player_id=player.id,
            status=BanStatus.ACTIVE,
            scope="global",
            scope_id=None,
            reason="Test ban reason",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
            issued_by=admin_user.id,
        )
        session.add(ban)

        # Update player status
        player.status = PlayerStatus.BANNED
        session.add(player)
        await session.commit()
        await session.refresh(ban)

        # Act
        revoked_ban = await admin_service.revoke_ban(
            ban_id=ban.id,
            reason="Ban incorrectly applied",
            actor=admin_user,
            session=session,
        )

        # Assert
        assert revoked_ban.status == BanStatus.REVOKED
        assert revoked_ban.revoked_by == admin_user.id
        assert revoked_ban.revoke_reason == "Ban incorrectly applied"

        # Verify player is active again
        await session.refresh(player)
        assert player.status == PlayerStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_revoke_ban_with_multiple_active_bans(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test revoking one ban when multiple active bans exist."""
        # Arrange - Create two bans
        player = test_players["regular_user"]

        # Create first ban
        ban1 = Ban(
            player_id=player.id,
            status=BanStatus.ACTIVE,
            scope="global",
            scope_id=None,
            reason="Test ban reason 1",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
            issued_by=admin_user.id,
        )
        session.add(ban1)

        # Create second ban
        ban2 = Ban(
            player_id=player.id,
            status=BanStatus.ACTIVE,
            scope="tournament",
            scope_id=str(uuid.uuid4()),
            reason="Test ban reason 2",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=15),
            issued_by=admin_user.id,
        )
        session.add(ban2)

        # Update player status
        player.status = PlayerStatus.BANNED
        session.add(player)
        await session.commit()
        await session.refresh(ban1)
        await session.refresh(ban2)

        # Act - Revoke one ban
        revoked_ban = await admin_service.revoke_ban(
            ban_id=ban1.id,
            reason="Ban incorrectly applied",
            actor=admin_user,
            session=session,
        )

        # Assert
        assert revoked_ban.status == BanStatus.REVOKED

        # Verify player is still banned due to other active ban
        await session.refresh(player)
        assert player.status == PlayerStatus.BANNED

    @pytest.mark.asyncio
    async def test_get_player_bans(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test retrieving player ban history."""
        # Arrange - Create multiple bans for a player
        player = test_players["regular_user"]

        # Create active ban
        active_ban = Ban(
            player_id=player.id,
            status=BanStatus.ACTIVE,
            scope="global",
            scope_id=None,
            reason="Active ban reason",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
            issued_by=admin_user.id,
        )
        session.add(active_ban)

        # Create revoked ban
        revoked_ban = Ban(
            player_id=player.id,
            status=BanStatus.REVOKED,
            scope="tournament",
            scope_id=str(uuid.uuid4()),
            reason="Revoked ban reason",
            start_date=datetime.now(timezone.utc) - timedelta(days=30),
            end_date=datetime.now(timezone.utc) + timedelta(days=15),
            issued_by=admin_user.id,
            revoked_by=admin_user.id,
            revoke_reason="Ban incorrectly applied",
        )
        session.add(revoked_ban)
        await session.commit()

        # Act - Get all bans including inactive
        all_bans = await admin_service.get_player_bans(
            player_id=player.id,
            include_inactive=True,
            session=session,
        )

        # Act - Get only active bans
        active_bans = await admin_service.get_player_bans(
            player_id=player.id,
            include_inactive=False,
            session=session,
        )

        # Assert
        assert len(all_bans) == 2
        assert len(active_bans) == 1
        assert any(ban.status == BanStatus.ACTIVE for ban in all_bans)
        assert any(ban.status == BanStatus.REVOKED for ban in all_bans)
        assert all(ban.status == BanStatus.ACTIVE for ban in active_bans)

    @pytest.mark.asyncio
    async def test_assign_role(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        test_roles: dict[str, Role],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test assigning a role to a player."""
        # Arrange
        from auth.schemas import PlayerRoleAssign

        player = test_players["regular_user"]
        role = test_roles["admin"]

        role_data = PlayerRoleAssign(
            role_id=str(role.id),
            scope_type=ScopeType.GLOBAL,
            scope_id=None,
        )

        # Act
        updated_player = await admin_service.assign_role(
            player_id=player.id,
            role_data=role_data,
            actor=admin_user,
            session=session,
        )

        # Assert
        assert updated_player.id == player.id

        # Verify player has the assigned role

        has_permissions = await admin_service.auth_service.verify_permissions(
            player=updated_player,
            permissions=["admin"],
            permission_scope=PermissionScope(ScopeType.GLOBAL, None),
            session=session,
        )

        assert has_permissions is True

    @pytest.mark.asyncio
    async def test_assign_role_player_not_found(
        self,
        admin_service: AdminService,
        test_roles: dict[str, Role],
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test role assignment fails for non-existent player."""
        # Arrange
        from auth.schemas import PlayerRoleAssign

        non_existent_id = uuid.uuid4()
        role = test_roles["admin"]

        role_data = PlayerRoleAssign(
            role_id=str(role.id),
            scope_type=ScopeType.GLOBAL,
            scope_id=None,
        )

        # Mock auth_service.get_player_by_id to return None
        admin_service.auth_service.get_player_by_id = AsyncMock(return_value=None)

        # Act & Assert
        with pytest.raises(AdminServiceError, match="Player not found"):
            await admin_service.assign_role(
                player_id=non_existent_id,
                role_data=role_data,
                actor=admin_user,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_force_remove_from_teams(
        self,
        admin_service: AdminService,
        test_players: dict[str, Player],
        test_team: Team,
        test_season: dict,
        admin_user: Player,
        session: AsyncSession,
    ):
        """Test forcing removal of a player from all teams."""
        # Arrange - Add player to team first
        from services.captain import captain_service
        from services.roster import roster_service

        player = test_players["another_user"]

        # Add as regular player
        await roster_service.add_player_to_team(
            team=test_team,
            player=player,
            season=test_season,
            actor=admin_user,
            session=session,
        )

        # Also add as captain
        await captain_service.add_captain(
            team=test_team,
            player=player,
            actor=admin_user,
            session=session,
        )

        # Act
        await admin_service.force_remove_from_teams(
            player_id=player.id,
            reason="Administrative action",
            actor=admin_user,
            session=session,
        )

        # Assert - Check roster status
        from teams.models import Roster

        roster_stmt = select(Roster).where(
            Roster.player_id == player.id,
            Roster.team_id == test_team.id
        )
        result = await session.execute(roster_stmt)
        roster = result.scalars().first()

        assert roster is not None
        assert roster.status == RosterStatus.INACTIVE

        # Check captain status
        from teams.models import TeamCaptain

        captain_stmt = select(TeamCaptain).where(
            TeamCaptain.player_id == player.id,
            TeamCaptain.team_id == test_team.id
        )
        result = await session.execute(captain_stmt)
        captaincy = result.scalars().first()

        assert captaincy is not None
        assert captaincy.status == TeamCaptainStatus.INACTIVE
