import logging
from typing import TypeVar

from status.pipeline_init import initialize_all_pipelines


LOG = logging.getLogger("uvicorn.error")
T = TypeVar("T")


def extend_status_transition_service(status_transition_service, **kwargs):
    """
    Extend the StatusTransitionService with pipeline functionality

    This function should be called during application startup to initialize
    all pipelines and attach them to the service
    """
    LOG.info("Extending StatusTransitionService with pipeline functionality")

    # Initialize all pipeline steps with additional services
    initialize_all_pipelines(status_transition_service, **kwargs)

    LOG.info("StatusTransitionService extended with pipeline functionality")
    return status_transition_service
