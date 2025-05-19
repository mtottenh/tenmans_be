import logging
from typing import Optional

from status.pipeline import TransitionPipeline
from status.transition_steps.team import (
    TeamFixtureForfeitStep,
    TeamRosterDeactivateStep,
    TeamCaptainDeactivateStep,
    TeamTournamentRegistrationStep
)
from status.transition_steps.team_permissions import TeamCaptainPermissionRevokeStep
from status.transition_steps.team_suspension import (
    TeamCaptainTemporaryStep,
    TeamFixtureRescheduleStep,
    TeamCaptainReactivateStep
)
from teams.base_schemas import TeamStatus

LOG = logging.getLogger('uvicorn.error')

def initialize_team_status_pipelines(status_transition_service, **kwargs) -> None:
    """Initialize all team status transition pipelines"""
    LOG.info("Initializing team status transition pipelines")
    
    # Get required services from kwargs
    permission_service = kwargs.get('permission_service')
    role_service = kwargs.get('role_service')
    
    # Team disbandment pipeline
    team_disband_pipeline = TransitionPipeline([
        TeamFixtureForfeitStep(),
        TeamRosterDeactivateStep(),
        TeamCaptainDeactivateStep(),
        TeamTournamentRegistrationStep(),
        TeamCaptainPermissionRevokeStep(permission_service, role_service) if permission_service and role_service else None
    ])
    # Filter out None values
    team_disband_pipeline.steps = [step for step in team_disband_pipeline.steps if step is not None]
    
    # Team suspension pipeline
    team_suspend_pipeline = TransitionPipeline([
        TeamCaptainTemporaryStep(),
        TeamFixtureRescheduleStep()
    ])
    
    # Team reactivation pipeline
    team_reactivate_pipeline = TransitionPipeline([
        TeamCaptainReactivateStep()
    ])
    
    # Register the pipelines with the service
    status_transition_service.register_transition_pipeline(
        entity_type="Team",
        new_status=TeamStatus.DISBANDED,
        pipeline=team_disband_pipeline
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Team",
        new_status=TeamStatus.SUSPENDED,
        pipeline=team_suspend_pipeline
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Team",
        new_status=TeamStatus.ACTIVE,
        pipeline=team_reactivate_pipeline
    )
    
    LOG.info("Team status transition pipelines initialized")


def initialize_tournament_status_pipelines(status_transition_service) -> None:
    """Initialize all tournament status transition pipelines"""
    LOG.info("Initializing tournament status transition pipelines")
    
    from status.transition_steps.tournament import (
        TournamentFixtureCancelStep,
        TournamentRegistrationCancelStep,
        TournamentRoundCompleteStep
    )
    from competitions.models.tournaments import TournamentState
    
    # Tournament cancellation pipeline
    tournament_cancel_pipeline = TransitionPipeline([
        TournamentFixtureCancelStep(),
        TournamentRegistrationCancelStep()
    ])
    
    # Tournament completion pipeline
    tournament_complete_pipeline = TransitionPipeline([
        TournamentRoundCompleteStep()
    ])
    
    # Register the pipelines with the service
    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.CANCELLED,
        pipeline=tournament_cancel_pipeline
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.COMPLETED,
        pipeline=tournament_complete_pipeline
    )
    
    LOG.info("Tournament status transition pipelines initialized")

# status/pipeline_init.py (additions)
def initialize_tournament_generation_pipelines(status_transition_service) -> None:
    """Initialize tournament generation status transition pipelines"""
    LOG.info("Initializing tournament generation status transition pipelines")
    
    from status.transition_steps.tournament_generation import (
        TournamentGenerationCleanupStep,
        TournamentGenerationValidationStep,
        TournamentRegistrationCloseStep,
        TournamentStartSetupStep
    )
    from competitions.models.tournaments import TournamentState
    
    # Registration close pipeline
    registration_close_pipeline = TransitionPipeline([
        TournamentRegistrationCloseStep()
    ])
    
    # Structure generation pipeline
    generation_pipeline = TransitionPipeline([
        TournamentGenerationCleanupStep(),
        TournamentGenerationValidationStep()
    ])
    
    # Tournament start pipeline
    tournament_start_pipeline = TransitionPipeline([
        TournamentStartSetupStep()
    ])
    
    # Register the pipelines
    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.REGISTRATION_CLOSED,
        pipeline=registration_close_pipeline
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.NOT_STARTED,
        pipeline=generation_pipeline
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.IN_PROGRESS,
        pipeline=tournament_start_pipeline
    )
    
    LOG.info("Tournament generation status transition pipelines initialized")


def initialize_player_status_pipelines(status_transition_service) -> None:
    """Initialize all player status transition pipelines"""
    LOG.info("Initializing player status transition pipelines")
    
    from status.transition_steps.player import (
        PlayerRosterDeactivateStep,
        PlayerCaptainDeactivateStep,
        PlayerFixtureSubstituteStep,
        PlayerRoleRemovalStep,
        PlayerUnbanRestoreStep
    )
    from auth.schemas import PlayerStatus
    
    # Player ban pipeline
    player_ban_pipeline = TransitionPipeline([
        PlayerRosterDeactivateStep(),
        PlayerCaptainDeactivateStep(),
        PlayerFixtureSubstituteStep(),
        PlayerRoleRemovalStep()
    ])
    
    # Player unban pipeline
    player_unban_pipeline = TransitionPipeline([
        PlayerUnbanRestoreStep()
    ])
    
    # Register the pipelines with the service
    status_transition_service.register_transition_pipeline(
        entity_type="Player",
        new_status=PlayerStatus.BANNED,
        pipeline=player_ban_pipeline
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Player",
        new_status=PlayerStatus.ACTIVE,
        pipeline=player_unban_pipeline
    )
    
    LOG.info("Player status transition pipelines initialized")

def initialize_map_pool_pipelines(status_transition_service) -> None:
    """Initialize map pool status transition pipelines"""
    LOG.info("Initializing map pool status transition pipelines")
    
    from status.transition_steps.map_pool import (
        MapPoolVotingCompleteStep,
        MapPoolNotificationStep
    )
    from competitions.map_pool.models import MapPoolStatus
    
    # Map pool finalization pipeline
    map_pool_finalize_pipeline = TransitionPipeline([
        MapPoolVotingCompleteStep(),
        MapPoolNotificationStep()
    ])
    
    # Register the pipeline
    status_transition_service.register_transition_pipeline(
        entity_type="TournamentMapPool",
        new_status=MapPoolStatus.FINALIZED,
        pipeline=map_pool_finalize_pipeline
    )
    
    LOG.info("Map pool status transition pipelines initialized")

def initialize_round_status_pipelines(status_transition_service) -> None:
    """Initialize all round status transition pipelines"""
    LOG.info("Initializing round status transition pipelines")
    
    from status.transition_steps.round import RoundCompleteStep
    
    # Round completion pipeline
    round_complete_pipeline = TransitionPipeline([
        RoundCompleteStep()
    ])
    
    # Register the pipeline
    status_transition_service.register_transition_pipeline(
        entity_type="Round",
        new_status="completed",
        pipeline=round_complete_pipeline
    )
    
    LOG.info("Round status transition pipelines initialized")
def initialize_all_pipelines(status_transition_service, **kwargs) -> None:
    """Initialize all status transition pipelines"""
    LOG.info("Initializing all status transition pipelines")
    
    # Initialize team pipelines with additional services
    initialize_team_status_pipelines(status_transition_service, **kwargs)
    
    # Initialize tournament pipelines
    initialize_tournament_status_pipelines(status_transition_service)
    
    # Initialize player pipelines
    initialize_player_status_pipelines(status_transition_service)
    
    # Initialize Map pool pipeline
    initialize_map_pool_pipelines(status_transition_service)
    # TODO: Initialize other entity type pipelines here
    # initialize_fixture_status_pipelines(status_transition_service)
    # Initialize round pipelines
    initialize_round_status_pipelines(status_transition_service)
    initialize_tournament_generation_pipelines(status_transition_service)
    LOG.info("All status transition pipelines initialized")