# tests/competitions/tournament/test_fixtures.py

import pytest

from competitions.models.fixtures import FixtureStatus
from matches.models import ConfirmationStatus, MatchFormat


@pytest.mark.asyncio
class TestTournamentFixtures:
    """Test fixture handling within tournaments"""

    async def test_fixture_generation(
        self, regular_tournament_setup, session, admin_user, tournament_service
    ):
        """Test generation of fixtures for regular tournament"""
        tournament = regular_tournament_setup["tournament"]
        service = tournament_service

        # Teams are already registered in the tournament setup
        # Generate tournament structure directly
        await service.generate_tournament_structure(
            tournament, admin_user, session
        )

        # Get rounds and verify structure
        rounds = await service._get_tournament_rounds(tournament, session)
        assert len(rounds) > 0  # Should have at least one round

        # Verify fixture generation
        total_teams = len(regular_tournament_setup["teams"])
        expected_fixtures_per_round = total_teams // 2  # Each team plays one match

        # Check each round has correct fixtures
        for round in rounds:
            fixtures = await service._get_round_fixtures(round.id, session)
            assert len(fixtures) == expected_fixtures_per_round

            # Verify fixture details
            for fixture in fixtures:
                assert fixture.tournament == tournament
                assert fixture.round_id == round.id
                assert fixture.status == FixtureStatus.SCHEDULED
                assert fixture.match_format in [MatchFormat.BO1, MatchFormat.BO3]
                assert fixture.team_1 != fixture.team_2  # Teams can't play themselves

                # Teams should be from registered teams
                team_ids = {t.id for t in regular_tournament_setup["teams"]}
                assert fixture.team_1 in team_ids
                assert fixture.team_2 in team_ids

    @pytest.mark.asyncio
    async def test_round_completion_with_results(
        self, regular_tournament_setup, session, admin_user, tournament_service
    ):
        """Test completing a round with submitted and confirmed results"""
        tournament = regular_tournament_setup["tournament"]
        builder = regular_tournament_setup["builder"]
        service = tournament_service

        # Teams are already registered in the tournament setup
        # Generate tournament structure directly
        await service.generate_tournament_structure(tournament, admin_user, session)

        # Start the tournament
        await service.start_tournament(tournament, admin_user, session)

        # Get the first round and its fixtures
        first_round = await service._get_round_by_number(tournament.id, 1, session)
        fixtures = await service._get_round_fixtures(first_round.id, session)

        # Complete all fixtures with results
        for fixture in fixtures:
            # Update fixture status to completed
            fixture.status = FixtureStatus.COMPLETED
            session.add(fixture)

            # Create winning results for team 1
            await builder.create_match_result(
                fixture=fixture,
                team_1_score=16,
                team_2_score=14,
                submitting_player=admin_user,
                map_number=1,
                status=ConfirmationStatus.CONFIRMED,
            )

        await session.commit()

        # Verify round can be completed
        await service.complete_round(tournament.id, 1, admin_user, session)

        # Check round status
        completed_round = await service._get_round_by_number(tournament.id, 1, session)
        assert completed_round.status == "completed"

    @pytest.mark.asyncio
    async def test_fixture_forfeits(
        self, regular_tournament_setup, session, admin_user, tournament_service
    ):
        """Test handling of forfeited fixtures"""
        tournament = regular_tournament_setup["tournament"]
        builder = regular_tournament_setup["builder"]
        service = tournament_service

        # Teams are already registered in the tournament setup
        # Generate tournament structure directly
        await service.generate_tournament_structure(tournament, admin_user, session)

        # Start the tournament
        await service.start_tournament(tournament, admin_user, session)

        # Get the first round and its fixtures
        first_round = await service._get_round_by_number(tournament.id, 1, session)
        fixtures = await service._get_round_fixtures(first_round.id, session)

        # Process fixtures - mix of forfeits and completed
        # First two are completed normally
        for i in range(2):
            fixtures[i].status = FixtureStatus.COMPLETED
            session.add(fixtures[i])
            await builder.create_match_result(
                fixture=fixtures[i],
                team_1_score=16,
                team_2_score=14,
                submitting_player=admin_user,
                map_number=1,
                status=ConfirmationStatus.CONFIRMED,
            )

        # Last two are forfeited
        for i in range(2, len(fixtures)):
            fixtures[i].status = FixtureStatus.FORFEITED
            fixtures[i].forfeit_winner = fixtures[i].team_1
            fixtures[i].forfeit_reason = "Team did not show up"
            session.add(fixtures[i])

        await session.commit()

        # Complete round
        await service.complete_round(tournament.id, 1, admin_user, session)

        # Verify standings include forfeits correctly
        standings = await service.get_tournament_standings(tournament.id, session)

        # Team that won normally and team that won by forfeit should have wins
        team_standings = {team.team_id: team for team in standings.teams}

        # Check wins for teams that won normally (first two fixtures)
        for i in range(2):
            winning_team = fixtures[i].team_1
            losing_team = fixtures[i].team_2
            assert team_standings[winning_team].matches_won == 1
            assert team_standings[losing_team].matches_lost == 1

        # Check wins for teams that won by forfeit (last fixtures)
        for i in range(2, len(fixtures)):
            winning_team = fixtures[i].team_1  # Won by forfeit
            losing_team = fixtures[i].team_2  # Lost by forfeit
            assert team_standings[winning_team].matches_won == 1
            assert team_standings[losing_team].matches_lost == 1

    @pytest.mark.asyncio
    async def test_knockout_round_progression(
        self, knockout_tournament_setup, session, admin_user, tournament_service
    ):
        """Test progression through knockout tournament rounds"""
        tournament = knockout_tournament_setup["tournament"]
        builder = knockout_tournament_setup["builder"]
        service = tournament_service

        # The tournament setup already has teams registered
        # Generate tournament structure directly
        await service.generate_tournament_structure(tournament, admin_user, session)

        # Start the tournament
        await service.start_tournament(tournament, admin_user, session)

        # Get first round fixtures
        round1 = await service._get_round_by_number(tournament.id, 1, session)
        fixtures = await service._get_round_fixtures(round1.id, session)

        # Complete all first round fixtures with team 1 winning each time
        winners = []

        for fixture in fixtures:
            fixture.status = FixtureStatus.COMPLETED
            session.add(fixture)

            # First team wins
            await builder.create_match_result(
                fixture=fixture,
                team_1_score=16,
                team_2_score=14,
                submitting_player=admin_user,
                map_number=1,
                status=ConfirmationStatus.CONFIRMED,
            )
            winners.append(fixture.team_1)

        await session.commit()

        # Complete first round - this should generate second round fixtures
        await service.complete_round(tournament.id, 1, admin_user, session)

        # Verify second round created with winners
        round2 = await service._get_round_by_number(tournament.id, 2, session)
        assert round2 is not None
        assert round2.status == "active"

        second_round_fixtures = await service._get_round_fixtures(round2.id, session)

        # Should be half as many fixtures with correct teams
        assert len(second_round_fixtures) == len(fixtures) // 2

        # Winners should be matched up
        fixture_teams = set()
        for f in second_round_fixtures:
            fixture_teams.add(f.team_1)
            fixture_teams.add(f.team_2)

        assert fixture_teams == set(winners)
