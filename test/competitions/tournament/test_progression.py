# tests/competitions/tournament/test_progression.py
import pytest
from datetime import datetime, timedelta
import uuid
import pytest_asyncio
from competitions.models.tournaments import TournamentState
from competitions.models.rounds import RoundType
from competitions.models.fixtures import FixtureStatus
from competitions.tournament.service import TournamentService, TournamentServiceError
from competitions.tournament.standings import RegularStandingsCalculator, KnockoutStandingsCalculator

@pytest.mark.asyncio
class TestTournamentProgression:
    """Test tournament progression through rounds"""
    @pytest.mark.asyncio
    async def test_start_tournament(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test starting a tournament activates first round"""
        # Setup
        tournament = regular_tournament_setup['tournament']
        tournament.state = TournamentState.REGISTRATION_CLOSED
        service = TournamentService()
        
        # Generate tournament structure
        tournament = await service.generate_tournament_structure(
            tournament.id,
            admin_user,
            session
        )
        
        # Start tournament
        started_tournament = await service.start_tournament(
            tournament.id,
            admin_user,  
            session
        )
        
        # Verify tournament state
        assert started_tournament.state == TournamentState.IN_PROGRESS
        assert started_tournament.actual_start_date is not None
        
        # Verify first round is active
        rounds = await service._get_tournament_rounds(tournament.id, session)
        first_round = min(rounds, key=lambda r: r.round_number)
        assert first_round.status == "active"
        
        # Verify other rounds are pending
        other_rounds = [r for r in rounds if r != first_round]
        assert all(r.status == "pending" for r in other_rounds)
    @pytest.mark.asyncio
    async def test_complete_regular_round(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test completing a round in regular tournament"""
        tournament = regular_tournament_setup['tournament']
        builder = regular_tournament_setup['builder']
        service = TournamentService()

        tournament.state = TournamentState.IN_PROGRESS
        session.add(tournament)
        await session.commit()

        round = await builder.create_round(
            tournament=tournament,
            round_number=1,
            round_type=RoundType.GROUP_STAGE,
            status="active",
        )

        teams = builder.teams[:4]  # First 4 teams
        for i in range(0, len(teams), 2):
            fixture = await builder.create_fixture_with_results(
                tournament=tournament,
                round=round,
                team_1=teams[i],
                team_2=teams[i+1],
                team_1_wins=2,  # Win 2-0
                user=admin_user
            )[0]

        updated_tournament = await service.complete_round(
            tournament.id,
            1,
            admin_user,
            session
        )

        completed_round = await service._get_round_by_number(tournament.id, 1, session)
        assert completed_round.status == "completed"

        next_round = await service._get_round_by_number(tournament.id, 2, session)
        if next_round:
            assert next_round.status == "active"
    @pytest.mark.asyncio
    async def test_complete_knockout_round(
        self,
        knockout_tournament_setup,
        session,
        admin_user
    ):
        """Test completing a round in knockout tournament"""
        tournament = knockout_tournament_setup['tournament']
        builder = knockout_tournament_setup['builder']
        service = TournamentService()
        
        tournament.state = TournamentState.IN_PROGRESS
        session.add(tournament)
        await session.commit()

        # First round
        round = await builder.create_round(
            tournament=tournament,
            round_number=1,
            round_type=RoundType.KNOCKOUT,
            status="active",
        )

        # Setup next round for winners
        next_round = await builder.create_round(
            tournament=tournament,
            round_number=2,
            round_type=RoundType.KNOCKOUT,
            status="pending",
        )

        # Create fixtures with alternating winners
        teams = builder.teams[:4]
        winners = []
        for i in range(0, len(teams), 2):
            fixture, results = await builder.create_fixture_with_results(
                tournament=tournament,
                round=round,
                team_1=teams[i],
                team_2=teams[i+1],
                team_1_wins=2 if i % 4 == 0 else 0,  # Alternate winners
                user=admin_user
            )
            winners.append(teams[i] if i % 4 == 0 else teams[i+1])

        # Complete first round
        updated_tournament = await service.complete_round(
            tournament.id,
            1,
            admin_user,
            session
        )

        # Verify round completion
        completed_round = await service._get_round_by_number(tournament.id, 1, session)
        assert completed_round.status == "completed"

        # Verify next round
        next_round = await service._get_round_by_number(tournament.id, 2, session)
        assert next_round.status == "active"

        # Verify next round fixtures
        next_fixtures = await service._get_round_fixtures(next_round.id, session)
        next_round_teams = {f.team_1 for f in next_fixtures} | {f.team_2 for f in next_fixtures}
        winner_ids = {t.id for t in winners}
        assert next_round_teams == winner_ids
    @pytest.mark.asyncio
    async def test_forfeit_handling(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test handling of forfeited matches in round completion"""
        tournament = regular_tournament_setup['tournament']
        builder = regular_tournament_setup['builder']
        service = TournamentService()

        tournament.state = TournamentState.IN_PROGRESS
        session.add(tournament)
        await session.commit()

        round = await builder.create_round(
            tournament=tournament,
            round_number=1,
            round_type=RoundType.GROUP_STAGE,
            status="active",
        )

        teams = builder.teams[:4]

        # Create one normal fixture
        await builder.create_fixture_with_results(
            tournament=tournament,
            round=round,
            team_1=teams[0],
            team_2=teams[1],
            team_1_wins=2,
            user=admin_user
        )

        # Create one forfeited fixture
        await builder.create_forfeited_fixture(
            tournament=tournament,
            round=round,
            team_1=teams[2],
            team_2=teams[3],
            forfeit_winner=teams[2],
            forfeit_reason="Team did not show"
        )

        # Complete round
        updated_tournament = await service.complete_round(
            tournament.id,
            1,
            admin_user,
            session
        )

        # Verify standings include forfeits correctly
        standings = await service.get_tournament_standings(tournament.id, session)
        team_standings = {team.team_id: team for team in standings.teams}
        
        # Teams 0 and 2 should have wins
        assert team_standings[teams[0].id].matches_won == 1  # Normal win
        assert team_standings[teams[2].id].matches_won == 1  # Forfeit win
        
        # Teams 1 and 3 should have losses 
        assert team_standings[teams[1].id].matches_lost == 1  # Normal loss
        assert team_standings[teams[3].id].matches_lost == 1  # Forfeit loss
    @pytest.mark.asyncio
    async def test_incomplete_round_completion(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test trying to complete a round with unfinished matches"""
        tournament = regular_tournament_setup['tournament']
        builder = regular_tournament_setup['builder']
        service = TournamentService()

        tournament.state = TournamentState.IN_PROGRESS
        session.add(tournament)
        await session.commit()

        round = await builder.create_round(
            tournament=tournament,
            round_number=1,
            round_type=RoundType.GROUP_STAGE,
            status="active",
        )

        teams = builder.teams[:4]

        # Create one completed fixture
        await builder.create_fixture_with_results(
            tournament=tournament,
            round=round,
            team_1=teams[0],
            team_2=teams[1],
            team_1_wins=2,
            user=admin_user
        )

        # Create one incomplete fixture
        await builder.create_fixture(
            tournament=tournament,
            round=round,
            team_1=teams[2],
            team_2=teams[3],
            status=FixtureStatus.SCHEDULED,
        )

        # Attempt to complete round

        with pytest.raises(TournamentServiceError, match="\d+ fixtures still pending completion"):
            await service.complete_round(tournament.id,  1, admin_user,  session)
    @pytest.mark.asyncio
    async def test_final_round_completion(
        self,
        knockout_tournament_setup,
        session,
        admin_user
    ):
        """Test completing final round of tournament"""
        tournament = knockout_tournament_setup['tournament']
        builder = knockout_tournament_setup['builder']
        service = TournamentService()

        tournament.state = TournamentState.IN_PROGRESS
        session.add(tournament)
        await session.commit()

        final_round = await builder.create_round(
            tournament=tournament,
            round_number=3,  # Finals
            round_type=RoundType.KNOCKOUT,
            status="active",
        )

        # Create and complete final fixture
        final_fixture, results = await builder.create_fixture_with_results(
            tournament=tournament,
            round=final_round,
            team_1=builder.teams[0],
            team_2=builder.teams[1],
            team_1_wins=2,  # Team 1 wins finals
            user=admin_user
        )

        # Complete final round
        updated_tournament = await service.complete_round(
            tournament.id,
            3,
            admin_user,
            session
        )

        # Verify tournament completion
        assert updated_tournament.state == TournamentState.COMPLETED
        assert updated_tournament.actual_end_date is not None
        
        # Verify final standings
        standings = await service.get_tournament_standings(tournament.id, session)
        team_standings = {team.team_id: team for team in standings.teams}
        
        # Winner should be team 1
        assert team_standings[builder.teams[0].id].final_position == 1
        assert team_standings[builder.teams[1].id].final_position == 2