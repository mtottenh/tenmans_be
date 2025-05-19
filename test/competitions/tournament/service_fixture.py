"""Fixture to create a properly configured TournamentService for tests"""

import pytest_asyncio

from audit.service import AuditService
from competitions.tournament.service import TournamentService
from status.pipeline_integration import extend_status_transition_service
from status.service import StatusTransitionService


@pytest_asyncio.fixture
async def tournament_service():
    """Create a fully configured TournamentService with all dependencies"""
    # Create and setup StatusTransitionService
    status_transition_service = StatusTransitionService()
    extend_status_transition_service(status_transition_service)

    # Create AuditService
    audit_service = AuditService()

    # Create TournamentService with all dependencies
    service = TournamentService(
        status_transition_service=status_transition_service, audit_service=audit_service
    )

    return service
