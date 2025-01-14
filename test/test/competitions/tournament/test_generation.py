# tests/competitions/tournament/test_generation.py
import pytest
from datetime import datetime, timedelta
import uuid
import pytest_asyncio
from competitions.models.tournaments import TournamentState
from competitions.models.rounds import RoundType
from competitions.models.fixtures import FixtureStatus
from competitions.tournament.service import TournamentService, TournamentServiceError

@pytest.mark.asyncio
class TestTournamentGeneration:
    """Test tournament structure generation"""

    async def test_regular_tournament_generation(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test generation of regular tournament structure"""
        tournament = regular_tournament_setup['tournament']
        tournament.state = TournamentState.REGISTRATION_CLOSED
        session.add(tournament)
        await session.commit()
        
        service = TournamentService()
        generated = await service.generate_tournament_structure(
            tournament.id,
            admin_user,
            session
        )
        
        # Verify tournament state
        assert generated.state == TournamentState.NOT_STARTED
        assert generated.actual_start_date is not None
        
        # Get rounds
        rounds = await service._get_tournament_rounds(tournament.id, session)
        
        # Verify round structure
        assert len(rounds) > 0
        assert all(r.type == RoundType.GROUP_STAGE for r in rounds)
        assert all(r.status == "pending" for r in rounds)
        
        # Verify fixture generation
        for round in rounds:
            fixtures = await service._get_round_fixtures(round.id, session)
            assert len(fixtures) > 0
            assert all(f.status == FixtureStatus.SCHEDULED for f in fixtures)
            # Verify teams are properly assigned
            team_ids = set(regular_tournament_setup['teams'])
            fixture_teams = {f.team_1 for f in fixtures} | {f.team_2 for f in fixtures}
            assert team_ids == fixture_teams

    async def test_knockout_tournament_generation(
        self,
        knockout_tournament_setup,
        session,
        admin_user
    ):
        """Test generation of knockout tournament structure"""
        tournament = knockout_tournament_setup['tournament']
        tournament.state = TournamentState.REGISTRATION_CLOSED
        session.add(tournament)
        await session.commit()
        
        service = TournamentService()
        generated = await service.generate_tournament_structure(
            tournament.id,
            admin_user,
            session
        )
        
        # Verify tournament state
        assert generated.state == TournamentState.NOT_STARTED
        
        # Get rounds
        rounds = await service._get_tournament_rounds(tournament.id, session)
        
        # Verify round structure
        assert len(rounds) == len(knockout_tournament_setup['teams']).bit_length() - 1  # Log2 ceiling
        assert all(r.type == RoundType.KNOCKOUT for r in rounds)
        
        # Verify fixture generation for first round
        first_round = rounds[0]
        fixtures = await service._get_round_fixtures(first_round.id, session)
        assert len(fixtures) == len(knockout_tournament_setup['teams']) // 2
        
        # Verify team assignments
        team_ids = {t.id for t in knockout_tournament_setup['teams']}
        first_round_teams = {f.team_1 for f in fixtures} | {f.team_2 for f in fixtures}
        assert team_ids == first_round_teams

    async def test_invalid_tournament_state(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test generation fails for invalid tournament state"""
        tournament = regular_tournament_setup['tournament']
        service = TournamentService()
        
        with pytest.raises(TournamentServiceError, match="Tournament must be in REGISTRATION_CLOSED state"):
            await service.generate_tournament_structure(
                tournament.id,
                admin_user,
                session
            )

    @pytest.mark.parametrize("team_count,min_teams,should_raise", [
        (2, 4, True),   # Too few teams
        (20, 16, True), # Too many teams
        (8, 4, False),  # Valid number of teams
    ])
    async def test_team_count_validation(
        self,
        test_data_builder,
        session,
        admin_user,
        team_count,
        min_teams,
        should_raise
    ):
        """Test validation of team counts"""
        # Setup tournament with specific requirements
        teams = await test_data_builder.create_teams(team_count, session)
        tournament = await test_data_builder.create_regular_tournament(
            team_count, session

        )
        tournament.min_teams = min_teams
        tournament.state = TournamentState.REGISTRATION_CLOSED
        
        # Add to session
        for team in teams:
            session.add(team)
        session.add(tournament)
        await session.commit()
        
        service = TournamentService()
        
        if should_raise:
            with pytest.raises(TournamentServiceError):
                await service.generate_tournament_structure(
                    tournament.id,
                    admin_user,
                    session
                )
        else:
            generated = await service.generate_tournament_structure(
                tournament.id,
                admin_user,
                session
            )
            assert generated.state == TournamentState.NOT_STARTED

    async def test_round_date_generation(
        self,
        regular_tournament_setup,
        session,
        admin_user
    ):
        """Test generated round dates are properly spaced"""
        tournament = regular_tournament_setup['tournament']
        tournament.state = TournamentState.REGISTRATION_CLOSED
        session.add(tournament)
        await session.commit()
        
        service = TournamentService()
        await service.generate_tournament_structure(
            tournament.id,
            admin_user,
            session
        )
        
        rounds = await service._get_tournament_rounds(tournament.id, session)
        rounds.sort(key=lambda r: r.round_number)
        
        # Verify round dates
        for i in range(len(rounds) - 1):
            assert rounds[i].end_date <= rounds[i + 1].start_date
            assert (rounds[i + 1].start_date - rounds[i].start_date).days == 7  # One week between rounds
            assert rounds[i].start_date >= tournament.scheduled_start_date
            assert rounds[i].end_date <= tournament.scheduled_end_date