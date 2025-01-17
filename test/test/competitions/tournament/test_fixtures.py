# tests/competitions/tournament/test_fixtures.py
import pytest
from datetime import datetime, timedelta
import uuid
import pytest_asyncio

from competitions.base_schemas import RegistrationStatus
from competitions.models.tournaments import Tournament, TournamentState, TournamentType
from competitions.models.rounds import Round, RoundType
from competitions.models.fixtures import Fixture, FixtureStatus
from competitions.tournament.schemas import TournamentRegistrationRequest
from matches.models import Result, ConfirmationStatus, MatchFormat
from competitions.tournament.service import TournamentService, TournamentServiceError
from test.test.competitions.tournament.conftest import TestDataBuilder

@pytest.mark.asyncio
class TestTournamentFixtures:
    """Test fixture handling within tournaments"""

    async def test_fixture_generation(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test generation of fixtures for regular tournament"""
        tournament = regular_tournament_setup['tournament']
        service = TournamentService()
        tournament.state = TournamentState.REGISTRATION_OPEN
        session.add(tournament)
        await session.commit()
        for team in regular_tournament_setup['teams']:
            rosters = await team.awaitable_attrs.rosters

            player = await rosters[0].awaitable_attrs.player
            await service.request_registration(TournamentRegistrationRequest(
                status=RegistrationStatus.APPROVED,
                team_id=team.id,
                notes=None,
                requested_by=player.uid,
                requested_at=datetime.now(),
                tournament_id=tournament.id
            ), player, session)
        tournament.state = TournamentState.REGISTRATION_CLOSED
        session.add(tournament)
        await session.commit()
        
        
        generated = await service.generate_tournament_structure(
            tournament.id,
            admin_user,
            session
        )
        
        # Get rounds and verify structure
        rounds = await service._get_tournament_rounds(tournament.id, session)
        assert len(rounds) > 0  # Should have at least one round
        
        # Verify fixture generation
        total_teams = len(regular_tournament_setup['teams'])
        expected_fixtures_per_round = total_teams // 2  # Each team plays one match
        
        # Check each round has correct fixtures
        for round in rounds:
            fixtures = await service._get_round_fixtures(round.id, session)
            assert len(fixtures) == expected_fixtures_per_round
            
            # Verify fixture details
            for fixture in fixtures:
                assert fixture.tournament_id == tournament.id
                assert fixture.round_id == round.id
                assert fixture.status == FixtureStatus.SCHEDULED
                assert fixture.match_format in [MatchFormat.BO1, MatchFormat.BO3]
                assert fixture.team_1 != fixture.team_2  # Teams can't play themselves
                
                # Teams should be from registered teams
                team_ids = {t.id for t in regular_tournament_setup['teams']}
                assert fixture.team_1 in team_ids
                assert fixture.team_2 in team_ids
    @pytest.mark.asyncio
    async def test_round_completion_with_results(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test completing a round with submitted and confirmed results"""
        tournament = regular_tournament_setup['tournament']
        builder = regular_tournament_setup['builder']
        service = TournamentService()
        
        # Setup tournament with completed matches
        tournament.state = TournamentState.IN_PROGRESS
        round = await builder.create_round(
            tournament=tournament,
            round_number=1,
            round_type=RoundType.GROUP_STAGE,
            status="active",
            
        )
        
        # Create and complete fixtures
        fixtures = []
        teams = regular_tournament_setup['teams'][:4]  # Use first 4 teams
        for i in range(0, len(teams), 2):
            fixture = await builder.create_fixture(
                tournament=tournament,
                round=round,
                team_1=teams[i],
                team_2=teams[i+1],
                status=FixtureStatus.COMPLETED,
                
            )
            
            # Create winning results for team 1
            await builder.create_match_result(
                fixture=fixture,
                team_1_score=16,
                team_2_score=14,
                submitting_player=admin_user,
                map_number=1,
                status=ConfirmationStatus.CONFIRMED
            )
            fixtures.append(fixture)
        
        # Verify round can be completed
        updated_tournament = await service.complete_round(
            tournament.id,
            1,
            admin_user,
            session
        )
        
        # Check round status
        completed_round = await service._get_round_by_number(
            tournament.id,
            1,
            session
        )
        assert completed_round.status == "completed"
    @pytest.mark.asyncio
    async def test_fixture_forfeits(
        self,
        regular_tournament_setup,
        session,
        admin_user  
    ):
        """Test handling of forfeited fixtures"""
        tournament = regular_tournament_setup['tournament']
        builder = regular_tournament_setup['builder']
        service = TournamentService()
        
        # Setup round
        tournament.state = TournamentState.IN_PROGRESS
        round = await builder.create_round(
            tournament=tournament,
            round_number=1,
            round_type=RoundType.GROUP_STAGE,
            status="active",
            
        )
        
        # Create fixtures - mix of forfeits and completed
        teams = regular_tournament_setup['teams'][:4]
        
        # Normal completed fixture
        fixture1 = await builder.create_fixture(
            tournament=tournament,
            round=round,
            team_1=teams[0],
            team_2=teams[1],
            status=FixtureStatus.COMPLETED,
            
        )
        await builder.create_match_result(
            fixture=fixture1,
            team_1_score=16,
            team_2_score=14,
            submitting_player=admin_user,
            map_number=1,
            status=ConfirmationStatus.CONFIRMED
        )
        
        # Forfeited fixture
        fixture2 = await builder.create_fixture(
            tournament=tournament,
            round=round,
            team_1=teams[2],
            team_2=teams[3],
            status=FixtureStatus.FORFEITED,
            
        )
        fixture2.forfeit_winner = teams[2].id
        fixture2.forfeit_reason = "Team did not show up"
        session.add(fixture2)
        
        await session.commit()
        
        # Complete round
        updated_tournament = await service.complete_round(
            tournament.id,
            1,
            admin_user,
            session  
        )
        
        # Verify standings include forfeits correctly
        standings = await service.get_tournament_standings(tournament.id, session)
        
        # Team 0 and Team 2 should have wins
        team_standings = {team.team_id: team for team in standings.teams}
        assert team_standings[teams[0].id].matches_won == 1
        assert team_standings[teams[2].id].matches_won == 1  # Forfeit win
        
        # Team 1 and Team 3 should have losses
        assert team_standings[teams[1].id].matches_lost == 1
        assert team_standings[teams[3].id].matches_lost == 1  # Forfeit loss
    @pytest.mark.asyncio
    async def test_knockout_round_progression(
        self,
        knockout_tournament_setup,
        session,
        admin_user
    ):
        """Test progression through knockout tournament rounds"""
        tournament = knockout_tournament_setup['tournament']
        builder = knockout_tournament_setup['builder']
        service = TournamentService()
        
        # Setup first round
        tournament.state = TournamentState.IN_PROGRESS
        round1 = await builder.create_round(
            tournament=tournament,
            round_number=1,
            round_type=RoundType.KNOCKOUT,
            status="active",
        )
        
        # Create first round fixtures
        teams = knockout_tournament_setup['teams'][:4]
        fixtures = []
        winners = []
        
        for i in range(0, len(teams), 2):
            fixture = await builder.create_fixture(
                tournament=tournament,
                round=round1,
                team_1=teams[i],
                team_2=teams[i+1],
                status=FixtureStatus.COMPLETED,
            )
            # First team wins
            await builder.create_match_result(
                fixture=fixture,
                team_1_score=16,
                team_2_score=14,
                submitting_player=admin_user,
                map_number=1,
                status=ConfirmationStatus.CONFIRMED
            )
            winners.append(teams[i])
            fixtures.append(fixture)
        
        # Complete first round
        await service.complete_round(
            tournament.id,
            1,
            admin_user,
            session
        )
        
        # Verify second round created with winners
        round2 = await service._get_round_by_number(tournament.id, 2, session)
        assert round2 is not None
        assert round2.status == "active"
        
        second_round_fixtures = await service._get_round_fixtures(
            round2.id,
            session
        )
        
        # Should be half as many fixtures with correct teams
        assert len(second_round_fixtures) == len(fixtures) // 2
        
        # Winners should be matched up
        fixture_teams = {f.team_1 for f in second_round_fixtures} | {f.team_2 for f in second_round_fixtures}
        winner_ids = {t.id for t in winners}
        assert fixture_teams == winner_ids