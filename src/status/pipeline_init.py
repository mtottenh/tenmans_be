import logging

from status.pipeline import TransitionPipeline
from status.transition_steps.team import (
    TeamCaptainDeactivateStep,
    TeamFixtureForfeitStep,
    TeamRosterDeactivateStep,
    TeamTournamentRegistrationStep,
)
from status.transition_steps.team_permissions import TeamCaptainPermissionRevokeStep
from status.transition_steps.team_suspension import (
    TeamCaptainReactivateStep,
    TeamCaptainTemporaryStep,
    TeamFixtureRescheduleStep,
)
from teams.base_schemas import TeamStatus


LOG = logging.getLogger("uvicorn.error")


def initialize_team_status_pipelines(status_transition_service, **kwargs) -> None:
    """Initialize all team status transition pipelines"""
    LOG.info("Initializing team status transition pipelines")

    # Get required services from kwargs
    permission_service = kwargs.get("permission_service")
    role_service = kwargs.get("role_service")

    # Team disbandment pipeline
    team_disband_pipeline = TransitionPipeline(
        [
            TeamFixtureForfeitStep(),
            TeamRosterDeactivateStep(),
            TeamCaptainDeactivateStep(),
            TeamTournamentRegistrationStep(),
            TeamCaptainPermissionRevokeStep(permission_service, role_service)
            if permission_service and role_service
            else None,
        ]
    )
    # Filter out None values
    team_disband_pipeline.steps = [
        step for step in team_disband_pipeline.steps if step is not None
    ]

    # Team suspension pipeline
    team_suspend_pipeline = TransitionPipeline(
        [TeamCaptainTemporaryStep(), TeamFixtureRescheduleStep()]
    )

    # Team reactivation pipeline
    team_reactivate_pipeline = TransitionPipeline([TeamCaptainReactivateStep()])

    # Register the pipelines with the service
    status_transition_service.register_transition_pipeline(
        entity_type="Team",
        new_status=TeamStatus.DISBANDED,
        pipeline=team_disband_pipeline,
    )

    status_transition_service.register_transition_pipeline(
        entity_type="Team",
        new_status=TeamStatus.SUSPENDED,
        pipeline=team_suspend_pipeline,
    )

    status_transition_service.register_transition_pipeline(
        entity_type="Team",
        new_status=TeamStatus.ACTIVE,
        pipeline=team_reactivate_pipeline,
    )

    LOG.info("Team status transition pipelines initialized")


def initialize_tournament_status_pipelines(status_transition_service) -> None:
    """Initialize all tournament status transition pipelines"""
    LOG.info("Initializing tournament status transition pipelines")

    from competitions.models.tournaments import TournamentState
    from status.transition_steps.tournament import (
        TournamentFixtureCancelStep,
        TournamentRegistrationCancelStep,
        TournamentRoundCompleteStep,
    )

    # Tournament cancellation pipeline
    tournament_cancel_pipeline = TransitionPipeline(
        [TournamentFixtureCancelStep(), TournamentRegistrationCancelStep()]
    )

    # Tournament completion pipeline
    tournament_complete_pipeline = TransitionPipeline([TournamentRoundCompleteStep()])

    # Register the pipelines with the service
    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.CANCELLED,
        pipeline=tournament_cancel_pipeline,
    )

    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.COMPLETED,
        pipeline=tournament_complete_pipeline,
    )

    LOG.info("Tournament status transition pipelines initialized")


# status/pipeline_init.py (additions)
def initialize_tournament_generation_pipelines(status_transition_service) -> None:
    """Initialize tournament generation status transition pipelines"""
    LOG.info("Initializing tournament generation status transition pipelines")

    from competitions.models.tournaments import TournamentState
    from status.transition_steps.tournament_generation import (
        TournamentGenerationCleanupStep,
        TournamentGenerationValidationStep,
        TournamentRegistrationCloseStep,
        TournamentStartSetupStep,
    )

    # Registration close pipeline
    registration_close_pipeline = TransitionPipeline(
        [TournamentRegistrationCloseStep()]
    )

    # Structure generation pipeline
    generation_pipeline = TransitionPipeline(
        [TournamentGenerationCleanupStep(), TournamentGenerationValidationStep()]
    )

    # Tournament start pipeline
    tournament_start_pipeline = TransitionPipeline([TournamentStartSetupStep()])

    # Register the pipelines
    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.REGISTRATION_CLOSED,
        pipeline=registration_close_pipeline,
    )

    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.NOT_STARTED,
        pipeline=generation_pipeline,
    )

    status_transition_service.register_transition_pipeline(
        entity_type="Tournament",
        new_status=TournamentState.IN_PROGRESS,
        pipeline=tournament_start_pipeline,
    )

    LOG.info("Tournament generation status transition pipelines initialized")


def initialize_player_status_pipelines(status_transition_service) -> None:
    """Initialize all player status transition pipelines"""
    LOG.info("Initializing player status transition pipelines")

    from auth.schemas import PlayerStatus
    from status.transition_steps.player import (
        PlayerCaptainDeactivateStep,
        PlayerFixtureSubstituteStep,
        PlayerRoleRemovalStep,
        PlayerRosterDeactivateStep,
        PlayerUnbanRestoreStep,
    )

    # Player ban pipeline
    player_ban_pipeline = TransitionPipeline(
        [
            PlayerRosterDeactivateStep(),
            PlayerCaptainDeactivateStep(),
            PlayerFixtureSubstituteStep(),
            PlayerRoleRemovalStep(),
        ]
    )

    # Player unban pipeline
    player_unban_pipeline = TransitionPipeline([PlayerUnbanRestoreStep()])

    # Register the pipelines with the service
    status_transition_service.register_transition_pipeline(
        entity_type="Player",
        new_status=PlayerStatus.BANNED,
        pipeline=player_ban_pipeline,
    )

    status_transition_service.register_transition_pipeline(
        entity_type="Player",
        new_status=PlayerStatus.ACTIVE,
        pipeline=player_unban_pipeline,
    )

    LOG.info("Player status transition pipelines initialized")


def initialize_map_pool_pipelines(status_transition_service) -> None:
    """Initialize map pool status transition pipelines"""
    LOG.info("Initializing map pool status transition pipelines")

    from competitions.map_pool.models import MapPoolStatus
    from status.transition_steps.map_pool import (
        MapPoolNotificationStep,
        MapPoolVotingCompleteStep,
    )

    # Map pool finalization pipeline
    map_pool_finalize_pipeline = TransitionPipeline(
        [MapPoolVotingCompleteStep(), MapPoolNotificationStep()]
    )

    # Register the pipeline
    status_transition_service.register_transition_pipeline(
        entity_type="TournamentMapPool",
        new_status=MapPoolStatus.FINALIZED,
        pipeline=map_pool_finalize_pipeline,
    )

    LOG.info("Map pool status transition pipelines initialized")


def initialize_round_status_pipelines(status_transition_service) -> None:
    """Initialize all round status transition pipelines"""
    LOG.info("Initializing round status transition pipelines")

    from status.transition_steps.round import RoundCompleteStep

    # Round completion pipeline
    round_complete_pipeline = TransitionPipeline([RoundCompleteStep()])

    # Register the pipeline
    status_transition_service.register_transition_pipeline(
        entity_type="Round", new_status="completed", pipeline=round_complete_pipeline
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
    # Initialize result and dispute pipelines
    initialize_result_status_pipelines(status_transition_service)
    initialize_dispute_status_pipelines(status_transition_service)
    LOG.info("All status transition pipelines initialized")


def initialize_result_status_pipelines(status_transition_service) -> None:
    """Initialize result status transition pipelines"""
    LOG.info("Initializing result status transition pipelines")
    
    from matches.models import ConfirmationStatus
    from status.transition_steps.result import (
        CreateDisputeStep,
        NotifyAdminsStep,
        NotifyOpposingTeamStep,
        RecalculateStandingsStep,
        UpdateFixtureStatusStep,
    )
    
    # Pending result submission pipeline
    pending_pipeline = TransitionPipeline([NotifyOpposingTeamStep()])
    
    # Result confirmation pipeline
    confirm_pipeline = TransitionPipeline([UpdateFixtureStatusStep()])
    
    # Result dispute pipeline
    dispute_pipeline = TransitionPipeline([CreateDisputeStep(), NotifyAdminsStep()])
    
    # Admin override pipeline
    override_pipeline = TransitionPipeline([UpdateFixtureStatusStep(), RecalculateStandingsStep()])
    
    # Void result pipeline
    void_pipeline = TransitionPipeline([UpdateFixtureStatusStep(), RecalculateStandingsStep()])
    
    # Register pipelines
    status_transition_service.register_transition_pipeline(
        entity_type="Result",
        new_status=ConfirmationStatus.PENDING,
        pipeline=pending_pipeline,
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Result",
        new_status=ConfirmationStatus.CONFIRMED,
        pipeline=confirm_pipeline,
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Result",
        new_status=ConfirmationStatus.DISPUTED,
        pipeline=dispute_pipeline,
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Result",
        new_status=ConfirmationStatus.ADMIN_OVERRIDE,
        pipeline=override_pipeline,
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="Result",
        new_status=ConfirmationStatus.VOIDED,
        pipeline=void_pipeline,
    )
    
    LOG.info("Result status transition pipelines initialized")


def initialize_dispute_status_pipelines(status_transition_service) -> None:
    """Initialize dispute status transition pipelines"""
    LOG.info("Initializing dispute status transition pipelines")
    
    from matches.models import DisputeStatus
    from status.transition_steps.dispute import (
        AssignReviewerStep,
        EscalateToHigherAuthorityStep,
        NotifyTeamsStep,
        RecordResolutionStep,
        UpdateResultStatusStep,
    )
    
    # Under review pipeline
    review_pipeline = TransitionPipeline([AssignReviewerStep()])
    
    # Dispute resolution pipeline
    resolve_pipeline = TransitionPipeline([
        UpdateResultStatusStep(),
        RecordResolutionStep(),
        NotifyTeamsStep(),
    ])
    
    # Dispute rejection pipeline
    reject_pipeline = TransitionPipeline([
        UpdateResultStatusStep(),
        RecordResolutionStep(),
        NotifyTeamsStep(),
    ])
    
    # Dispute escalation pipeline
    escalate_pipeline = TransitionPipeline([
        EscalateToHigherAuthorityStep(),
        NotifyTeamsStep(),
    ])
    
    # Register pipelines
    status_transition_service.register_transition_pipeline(
        entity_type="MatchDispute",
        new_status=DisputeStatus.UNDER_REVIEW,
        pipeline=review_pipeline,
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="MatchDispute",
        new_status=DisputeStatus.RESOLVED,
        pipeline=resolve_pipeline,
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="MatchDispute",
        new_status=DisputeStatus.REJECTED,
        pipeline=reject_pipeline,
    )
    
    status_transition_service.register_transition_pipeline(
        entity_type="MatchDispute",
        new_status=DisputeStatus.ESCALATED,
        pipeline=escalate_pipeline,
    )
    
    LOG.info("Dispute status transition pipelines initialized")
