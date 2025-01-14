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

    async def test_start_tournament(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test starting a tournament activates first round"""
        # Setup
        tournament = regular_tournament_setup['tournament']
        tournament.state = TournamentState.NOT_STARTED
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
        
        # Setup tournament with some completed matches
        tournament.state = TournamentState.IN_PROGRESS
        round = await builder.create_round(tournament, 1, RoundType.GROUP_STAGE, "active", session)
        
        # Create and complete fixtures
        fixtures = []
        for i in range(0, len(regular_tournament_setup['teams']), 2):
            fixture = await builder.create_fixture(
                tournament,
                round,
                regular_tournament_setup['teams'][i],
                regular_tournament_setup['teams'][i+1],
                FixtureStatus.COMPLETED,
                session
            )
            await builder.create_match_result(fixture, 16, 14, admin_user)
            fixtures.append(fixture)
            
        session.add(round)
        for fixture in fixtures:
            session.add(fixture)
        await session.commit()
        
        # Complete the round
        updated_tournament = await service.complete_round(
            tournament.id,
            1,
            admin_user,
            session
        )
        
        # Verify round status
        completed_round = await service._get_round_by_number(tournament.id, 1, session)
        assert completed_round.status == "completed"
        
        # Verify next round status
        next_round = await service._get_round_by_number(tournament.id, 2, session)
        if next_round:
            assert next_round.status == "active"

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
        
        # Setup tournament with completed matches
        tournament.state = TournamentState.IN_PROGRESS
        round = await builder.create_round(tournament, 1, RoundType.KNOCKOUT, "active")
        next_round = await builder.create_round(tournament, 2, RoundType.KNOCKOUT, "pending", session)
        
        # Create and complete fixtures
        fixtures = []
        winners = []
        for i in range(0, len(knockout_tournament_setup['teams']), 2):
            fixture = await builder.create_fixture(
                tournament,
                round,
                knockout_tournament_setup['teams'][i],
                knockout_tournament_setup['teams'][i+1],
                FixtureStatus.COMPLETED,
                session
            )
            # Alternate winners
            if i % 4 == 0:
                await builder.create_match_result(fixture, 16, 14, admin_user, session)
                winners.append(knockout_tournament_setup['teams'][i])
            else:
                await builder.create_match_result(fixture, 14, 16, admin_user, session)
                winners.append(knockout_tournament_setup['teams'][i+1])
            fixtures.append(fixture)
            
        session.add(round)
        session.add(next_round)
        for fixture in fixtures:
            session.add(fixture)
        await session.commit()
        
        # Complete the round
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
        
        # Setup round with mix of completed and forfeited matches
        tournament.state = TournamentState.IN_PROGRESS
        round = await builder.create_round(tournament, 1, RoundType.GROUP_STAGE, "active", session)
        
        fixtures = []
        for i in range(0, len(regular_tournament_setup['teams']), 2):
            fixture = await builder.create_fixture(
                tournament,
                round,
                regular_tournament_setup['teams'][i],
                regular_tournament_setup['teams'][i+1], session
            )
            if i < 2:
                # Normal completion
                fixture.status = FixtureStatus.COMPLETED
                await builder.create_match_result(fixture, 16, 14, admin_user, session)
            else:
                # Forfeit
                fixture.status = FixtureStatus.FORFEITED
                fixture.forfeit_winner = regular_tournament_setup['teams'][i].id
                await builder.create_forfeit_result(
                    fixture,
                    regular_tournament_setup['teams'][i].id,
                    admin_user, session
                )
            fixtures.append(fixture)
            
        session.add(round)
        for fixture in fixtures:
            session.add(fixture)
        await session.commit()
        
        # Complete round
        updated_tournament = await service.complete_round(
            tournament.id,
            1,
            admin_user,
            session
        )
        
        # Verify round completion
        completed_round = await service._get_round_by_number(tournament.id, 1, session)
        assert completed_round.status == "completed"

    async def test_incomplete_round_completion(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test attempting to complete round with incomplete matches"""
        tournament = regular_tournament_setup['tournament']
        builder = regular_tournament_setup['builder']
        service = TournamentService()
        
        # Setup round with incomplete matches
        tournament.state = TournamentState.IN_PROGRESS
        round = await builder.create_round(tournament, 1, RoundType.GROUP_STAGE, "active", session)
        
        fixtures = []
        for i in range(0, len(regular_tournament_setup['teams']), 2):
            fixture = await builder.create_fixture(
                tournament,
                round,
                regular_tournament_setup['teams'][i],
                regular_tournament_setup['teams'][i+1], session
            )
            if i == 0:
                # One completed match
                fixture.status = FixtureStatus.COMPLETED
                await builder.create_match_result(fixture, 16, 14, admin_user, session)
            else:
                # Rest incomplete
                fixture.status = FixtureStatus.SCHEDULED
            fixtures.append(fixture)
            
        session.add(round)
        for fixture in fixtures:
            session.add(fixture)
        await session.commit()
        
        # Attempt to complete round
        with pytest.raises(TournamentServiceError, match="All fixtures must be completed"):
            await service.complete_round(
                tournament.id,
                1,
                admin_user,
                session
            )

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
        
        # Setup final round
        tournament.state = TournamentState.IN_PROGRESS
        final_round = await builder.create_round(tournament, 3, RoundType.KNOCKOUT, "active", session)
        
        # Create and complete final fixture
        final = await builder.create_fixture(
            tournament,
            final_round,
            knockout_tournament_setup['teams'][0],
            knockout_tournament_setup['teams'][1],
            FixtureStatus.COMPLETED, session
        )
        await builder.create_match_result(final, 16, 14, admin_user, session)
        
        session.add(final_round)
        session.add(final)
        await session.commit()
        
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