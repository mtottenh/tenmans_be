import pytest_asyncio
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime, timedelta
import uuid

from teams.join_request.models import TeamJoinRequest, JoinRequestStatus
from teams.join_request.service import TeamJoinRequestService, JoinRequestError
from teams.service import TeamService
from auth.models import Player, AuthType, VerificationStatus
from competitions.models.seasons import Season, SeasonState
from teams.models import Team, TeamCaptain

@pytest_asyncio.fixture
async def join_request_service():
    return TeamJoinRequestService()

@pytest_asyncio.fixture
async def team_service():
    return TeamService()

@pytest_asyncio.fixture
async def test_season(session: AsyncSession):
    season = Season(
        name="Test Season",
        state=SeasonState.IN_PROGRESS
    )
    session.add(season)
    await session.commit()
    await session.refresh(season)
    return season

@pytest_asyncio.fixture
async def test_team(session: AsyncSession):
    team = Team(
        name="Test Team",
        created_at=datetime.now()
    )
    session.add(team)
    await session.commit()
    await session.refresh(team)
    return team

@pytest_asyncio.fixture
async def team_captain(session: AsyncSession):
    captain = Player(
        name="Team Captain",
        steam_id="76561197971721557",
        auth_type=AuthType.STEAM,
        verification_status=VerificationStatus.VERIFIED
    )
    session.add(captain)
    await session.commit()
    await session.refresh(captain)
    return captain

@pytest_asyncio.fixture
async def test_player(session: AsyncSession):
    player = Player(
        name="Test Player",
        steam_id="76561197971721558",
        auth_type=AuthType.STEAM,
        verification_status=VerificationStatus.VERIFIED
    )
    session.add(player)
    await session.commit()
    await session.refresh(player)
    return player

@pytest_asyncio.fixture
async def setup_team_with_captain(
    session: AsyncSession,
    test_team: Team,
    team_captain: Player
):
    captain_entry = TeamCaptain(
        team_id=test_team.id,
        player_uid=team_captain.uid
    )
    session.add(captain_entry)
    await session.commit()
    return test_team, team_captain

@pytest.mark.asyncio
class TestTeamJoinRequest:
    async def test_create_join_request_success(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        test_team: Team,
        test_player: Player,
        test_season: Season
    ):
        """Test successful creation of join request"""
        # Create request
        request = await join_request_service.create_request(
            player=test_player,
            team=test_team,
            season=test_season,
            message="Please let me join!",
            actor=test_player,
            session=session
        )
        
        assert request is not None
        assert request.player_uid == test_player.uid
        assert request.team_id == test_team.id
        assert request.status == JoinRequestStatus.PENDING
        assert request.message == "Please let me join!"

    async def test_duplicate_join_request(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        test_team: Team,
        test_player: Player,
        test_season: Season
    ):
        """Test that players cannot submit duplicate requests"""
        # Create initial request
        await join_request_service.create_request(
            player=test_player,
            team=test_team,
            season=test_season,
            message="First request",
            actor=test_player,
            session=session
        )

        # Try to create duplicate request
        with pytest_asyncio.raises(JoinRequestError, match="Player already has an active join request"):
            await join_request_service.create_request(
                player=test_player,
                team=test_team,
                season=test_season,
                message="Second request",
                actor=test_player,
                session=session
            )

    async def test_approve_join_request(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        setup_team_with_captain,
        test_player: Player,
        test_season: Season
    ):
        """Test successful approval of join request by team captain"""
        team, captain = setup_team_with_captain

        # Create request
        request = await join_request_service.create_request(
            player=test_player,
            team=team,
            season=test_season,
            message="Please approve!",
            actor=test_player,
            session=session
        )

        # Approve request
        updated_request = await join_request_service.approve_request(
            request=request,
            captain=captain,
            response_message="Welcome to the team!",
            actor=captain,
            session=session
        )

        assert updated_request.status == JoinRequestStatus.APPROVED
        assert updated_request.responded_by == captain.uid
        assert updated_request.response_message == "Welcome to the team!"
        
        # Verify player was added to roster
        roster = await team.awaitable_attrs.rosters
        assert any(r.player_uid == test_player.uid for r in roster)

    async def test_reject_join_request(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        setup_team_with_captain,
        test_player: Player,
        test_season: Season
    ):
        """Test rejection of join request by team captain"""
        team, captain = setup_team_with_captain

        # Create request
        request = await join_request_service.create_request(
            player=test_player,
            team=team,
            season=test_season,
            message="Please let me join!",
            actor=test_player,
            session=session
        )

        # Reject request
        updated_request = await join_request_service.reject_request(
            request=request,
            captain=captain,
            response_message="Sorry, team is full",
            actor=captain,
            session=session
        )

        assert updated_request.status == JoinRequestStatus.REJECTED
        assert updated_request.responded_by == captain.uid
        assert updated_request.response_message == "Sorry, team is full"
        
        # Verify player was not added to roster
        roster = await team.awaitable_attrs.rosters
        assert not any(r.player_uid == test_player.uid for r in roster)

    async def test_non_captain_cannot_approve(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        test_team: Team,
        test_player: Player,
        team_captain: Player,  # Using as non-captain here
        test_season: Season
    ):
        """Test that non-captains cannot approve requests"""
        # Create request
        request = await join_request_service.create_request(
            player=test_player,
            team=test_team,
            season=test_season,
            message="Please approve!",
            actor=test_player,
            session=session
        )

        # Try to approve as non-captain
        with pytest.raises(JoinRequestError, match="Only team captains can review requests"):
            await join_request_service.approve_request(
                request=request,
                captain=team_captain,  # Not actually a captain
                response_message="Welcome!",
                actor=team_captain,
                session=session
            )

    async def test_cancel_join_request(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        test_team: Team,
        test_player: Player,
        test_season: Season
    ):
        """Test that players can cancel their own requests"""
        # Create request
        request = await join_request_service.create_request(
            player=test_player,
            team=test_team,
            season=test_season,
            message="Please let me join!",
            actor=test_player,
            session=session
        )

        # Cancel request
        cancelled_request = await join_request_service.cancel_request(
            request=request,
            player=test_player,
            actor=test_player,
            session=session
        )

        assert cancelled_request.status == JoinRequestStatus.CANCELLED
        assert cancelled_request.withdrawn_at is not None

    async def test_only_requester_can_cancel(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        test_team: Team,
        test_player: Player,
        team_captain: Player,
        test_season: Season
    ):
        """Test that only the requesting player can cancel their request"""
        # Create request
        request = await join_request_service.create_request(
            player=test_player,
            team=test_team,
            season=test_season,
            message="Please let me join!",
            actor=test_player,
            session=session
        )

        # Try to cancel as different player
        with pytest.raises(JoinRequestError, match="Only requesting player can cancel request"):
            await join_request_service.cancel_request(
                request=request,
                player=team_captain,
                actor=team_captain,
                session=session
            )

    async def test_cannot_approve_cancelled_request(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        setup_team_with_captain,
        test_player: Player,
        test_season: Season
    ):
        """Test that cancelled requests cannot be approved"""
        team, captain = setup_team_with_captain

        # Create and cancel request
        request = await join_request_service.create_request(
            player=test_player,
            team=team,
            season=test_season,
            message="Please let me join!",
            actor=test_player,
            session=session
        )

        await join_request_service.cancel_request(
            request=request,
            player=test_player,
            actor=test_player,
            session=session
        )

        # Try to approve cancelled request
        with pytest.raises(JoinRequestError, match="Can only review pending requests"):
            await join_request_service.approve_request(
                request=request,
                captain=captain,
                response_message="Welcome!",
                actor=captain,
                session=session
            )

    async def test_cleanup_expired_requests(
        self,
        session: AsyncSession,
        join_request_service: TeamJoinRequestService,
        test_team: Team,
        test_player: Player,
        test_season: Season
    ):
        """Test cleanup of expired join requests"""
        # Create old request with mocked creation date
        request = await join_request_service.create_request(
            player=test_player,
            team=test_team,
            season=test_season,
            message="Old request",
            actor=test_player,
            session=session
        )
        
        # Manually update created_at to be old
        request.created_at = datetime.now() - timedelta(days=10)
        session.add(request)
        await session.commit()

        # Run cleanup with 7 day expiry
        expired_count = await join_request_service.cleanup_expired_requests(
            session=session,
            expiry_days=7
        )

        assert expired_count == 1
        
        # Verify request is now expired
        await session.refresh(request)
        assert request.status == JoinRequestStatus.EXPIRED