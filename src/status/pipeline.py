import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from audit.context import AuditContext
from auth.models import Player


LOG = logging.getLogger("uvicorn.error")


class TransitionStep(ABC):
    """Base class for status transition pipeline steps"""

    @abstractmethod
    async def execute(
        self,
        entity: Any,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        context: dict = None,
    ) -> None:
        """Execute the pipeline step"""
        pass

    @property
    def step_name(self) -> str:
        """Get the name of this pipeline step"""
        return self.__class__.__name__


class TransitionPipeline:
    """A pipeline of transition steps to be executed during status transitions"""

    def __init__(self, steps: list[TransitionStep]):
        self.steps = steps

    async def execute(
        self,
        entity: Any,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context: Optional[AuditContext] = None,
        **context,
    ) -> None:
        """Execute all pipeline steps in sequence"""

        # Create a shared context dict that can be modified by steps
        shared_context = dict(context)
        
        for step in self.steps:
            LOG.info(f"Executing transition step: {step.step_name}")
            try:
                # Pass shared_context directly as a single parameter
                # rather than unpacking it with ** which creates a new dict
                await step.execute(
                    entity=entity,
                    old_status=old_status,
                    new_status=new_status,
                    actor=actor,
                    session=session,
                    audit_context=audit_context,
                    context=shared_context,
                )
            except Exception as e:
                LOG.error(f"Error in transition step {step.step_name}: {e!s}")
                # We rely on the audit_context to handle the rollback
                raise
                
        # Update the original context with any new values
        for key, value in shared_context.items():
            context[key] = value
