from typing import Dict, List, Optional, TypeVar, Any
import logging
from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from audit.models import AuditEvent, AuditEventType
from audit.service import AuditService
from auth.models import Player
from auth.service.permission import PermissionScope, PermissionService
from status.pipeline import TransitionPipeline, TransitionStep
from status.transition_validator import StatusTransitionManager, TransitionError
from status.pipeline_init import initialize_all_pipelines

LOG = logging.getLogger('uvicorn.error')
T = TypeVar('T')

def extend_status_transition_service(status_transition_service):
    """
    Extend the StatusTransitionService with pipeline functionality
    
    This function should be called during application startup to initialize
    all pipelines and attach them to the service
    """
    LOG.info("Extending StatusTransitionService with pipeline functionality")
    
    # Initialize all pipeline steps
    initialize_all_pipelines(status_transition_service)
    
    LOG.info("StatusTransitionService extended with pipeline functionality")
    return status_transition_service