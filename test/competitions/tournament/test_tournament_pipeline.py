"""Test for tournament pipeline with status transitions"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Player
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.models.rounds import Round, RoundType
from competitions.models.tournaments import Tournament, TournamentState
from competitions.rounds.round_winner_service import RoundWinnerService
from competitions.tournament.service import TournamentService
from status.service import create_enhanced_status_transition_service


@pytest_asyncio.fixture
async def tournament_round_setup(session: AsyncSession, admin_user: Player):
    """Set up tournament with rounds for pipeline testing"""
    # Create consistent timezone-aware timestamps
    now = datetime.now(timezone.utc)
    week_later = now + timedelta(days=7)
    two_weeks_later = now + timedelta(days=14)
    month_later = now + timedelta(days=30)

    # Create a season for referential integrity
    from competitions.models.seasons import Season
    
    season = Season(
        id=uuid.uuid4(),
        name="Test Season",
        status="active",
        start_date=now - timedelta(days=30),
        end_date=now + timedelta(days=60)
    )
    session.add(season)
    await session.flush()
    
    season_id = season.id

    # Create tournament with unique name to prevent conflicts
    tournament_name = f"Pipeline Test Tournament {uuid.uuid4()}"
    tournament = Tournament(
        id=uuid.uuid4(),
        name=tournament_name,
        season_id=season_id,
        type="regular",
        status=TournamentState.IN_PROGRESS,
        scheduled_start_date=now,
        scheduled_end_date=month_later,
        min_teams=2,
        max_teams=8,
        # Add required fields with default values
        registration_start=now - timedelta(days=10),
        registration_end=now - timedelta(days=5),
        format_config={"match_format": "bo1"},
        # Add required max_team_size field
        max_team_size=5
    )
    session.add(tournament)
    await session.flush()  # Flush to get the ID but don't commit yet

    # Create rounds with explicit unique IDs
    round1_id = uuid.uuid4()
    round1 = Round(
        id=round1_id,
        tournament_id=tournament.id,
        round_number=1,
        type=RoundType.GROUP_STAGE,
        best_of=1,
        status="active",
        start_date=now,
        end_date=week_later,
        created_at=now,
        updated_at=now
    )
    session.add(round1)

    round2_id = uuid.uuid4()
    round2 = Round(
        id=round2_id,
        tournament_id=tournament.id,
        round_number=2,
        type=RoundType.KNOCKOUT,
        best_of=3,
        status="pending",
        start_date=week_later,
        end_date=two_weeks_later,
        created_at=now,
        updated_at=now
    )
    session.add(round2)
    await session.flush()

    # Create teams with unique IDs
    from teams.models import Team
    
    team1 = Team(
        id=uuid.uuid4(),
        name="Test Team 1",
        logo_path=None,
        captain_id=admin_user.id,
        status="active"
    )
    session.add(team1)
    
    team2 = Team(
        id=uuid.uuid4(),
        name="Test Team 2",
        logo_path=None,
        captain_id=admin_user.id,
        status="active"
    )
    session.add(team2)
    await session.flush()
    
    team1_id = team1.id
    team2_id = team2.id

    # Create a completed fixture with unique ID
    fixture_id = uuid.uuid4()
    fixture = Fixture(
        id=fixture_id,
        tournament_id=tournament.id,
        round_id=round1.id,
        team_1=team1_id,
        team_2=team2_id,
        status=FixtureStatus.COMPLETED,
        match_format="bo1",
        scheduled_at=now,
        created_at=now,
        updated_at=now,
        winner_id=team1_id  # Team 1 won
    )
    session.add(fixture)

    # Commit everything at once for transactional consistency
    await session.commit()

    # Refresh objects to ensure they have the latest state
    await session.refresh(tournament)
    await session.refresh(round1)
    await session.refresh(round2)
    await session.refresh(fixture)

    # Create service with proper pipeline support
    tournament_service = TournamentService(
        status_transition_service=create_enhanced_status_transition_service(),
        round_winner_service=RoundWinnerService()
    )

    return {
        "tournament": tournament,
        "round1": round1,
        "round2": round2,
        "fixture": fixture,
        "service": tournament_service,
        "team1_id": team1_id,
        "team2_id": team2_id
    }


@pytest.mark.asyncio
async def test_tournament_round_completion_pipeline(
    tournament_round_setup, admin_user, session
):
    """Test that completing a round activates the next round via pipeline"""
    data = tournament_round_setup
    tournament = data["tournament"]
    round1 = data["round1"]
    round2 = data["round2"]
    service = data["service"]

    # Complete the first round
    await service.complete_round(
        tournament_id=tournament.id, 
        round_number=1,
        actor=admin_user, 
        session=session
    )

    # Refresh from database
    await session.refresh(round1)
    await session.refresh(round2)

    # Verify round statuses
    assert round1.status == "completed"
    assert round2.status == "active"


@pytest.mark.asyncio
async def test_final_round_completion(
    tournament_round_setup, admin_user, session
):
    """Test that completing the final round completes the tournament"""
    data = tournament_round_setup
    tournament = data["tournament"]
    round2 = data["round2"]
    service = data["service"]

    # Set round 2 as active and mark it as the final round
    round2.status = "active"
    session.add(round2)
    await session.commit()

    # Complete round 2 (which should be the final round)
    await service.complete_round(
        tournament_id=tournament.id, 
        round_number=2,
        actor=admin_user, 
        session=session
    )

    # Refresh tournament
    await session.refresh(tournament)

    # Verify tournament status
    assert tournament.status == TournamentState.COMPLETED