"""Fixture to create a properly configured TournamentService for tests"""

import pytest_asyncio

from audit.service import AuditService
from competitions.rounds.round_winner_service import RoundWinnerService  
from competitions.tournament.service import TournamentService
from status.service import create_enhanced_status_transition_service


@pytest_asyncio.fixture
async def tournament_service():
    """Create a fully configured TournamentService with all dependencies"""
    # Create properly enhanced status transition service with pipeline support
    status_transition_service = create_enhanced_status_transition_service()

    # Create AuditService
    audit_service = AuditService()

    # Create RoundWinnerService
    round_winner_service = RoundWinnerService()

    # Create TournamentService with all dependencies
    service = TournamentService(
        status_transition_service=status_transition_service, 
        audit_service=audit_service,
        round_winner_service=round_winner_service
    )

    return service
