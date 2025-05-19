import pytest
import pytest_asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List

from status.pipeline import TransitionPipeline, TransitionStep
from audit.context import AuditContext
from audit.schemas import AuditEventType
from auth.models import Player


# Mock pipeline steps for testing
class RecordingStep(TransitionStep):
    """A step that records its execution"""
    
    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail
        self.executed = False
        self.execution_order = None
    
    async def execute(
        self,
        entity,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context=None,
        **context
    ) -> None:
        # Record execution
        self.executed = True
        
        # Track execution order
        if 'execution_counter' not in context:
            context['execution_counter'] = 0
        self.execution_order = context['execution_counter']
        context['execution_counter'] += 1
        
        # Store in shared list if provided
        if 'executed_steps' in context:
            context['executed_steps'].append(self.name)
        
        # Optionally fail
        if self.should_fail:
            raise RuntimeError(f"Step {self.name} failed as requested")
    
    @property
    def step_name(self) -> str:
        return self.name


class AuditingStep(TransitionStep):
    """A step that creates audit events"""
    
    async def execute(
        self,
        entity,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context=None,
        **context
    ) -> None:
        if audit_context:
            await audit_context.create_audit_event(
                session=session,
                action_type=AuditEventType.STATUS_CHANGE,
                entity_type=type(entity).__name__,
                entity_id=getattr(entity, 'id', None),
                actor=actor,
                details={"step": "auditing_step", "transition": f"{old_status} -> {new_status}"}
            )


class DataModificationStep(TransitionStep):
    """A step that modifies entity data"""
    
    async def execute(
        self,
        entity,
        old_status: str,
        new_status: str,
        actor: Player,
        session: AsyncSession,
        audit_context=None,
        **context
    ) -> None:
        # Modify the entity
        if hasattr(entity, 'metadata'):
            if entity.metadata is None:
                entity.metadata = {}
            entity.metadata['modified_by_pipeline'] = True
            entity.metadata['transition'] = f"{old_status} -> {new_status}"


class MockEntity:
    """Mock entity for testing"""
    def __init__(self, id=None):
        self.id = id or uuid4()
        self.status = "DRAFT"
        self.metadata = {}


class TestTransitionPipeline:
    """Test the TransitionPipeline functionality"""
    
    @pytest.mark.asyncio
    async def test_simple_pipeline_execution(self, session: AsyncSession, system_user: Player):
        """Test basic pipeline execution with multiple steps"""
        # Create steps
        step1 = RecordingStep("step1")
        step2 = RecordingStep("step2")
        step3 = RecordingStep("step3")
        
        # Create pipeline
        pipeline = TransitionPipeline([step1, step2, step3])
        
        # Create entity
        entity = MockEntity()
        
        # Context to track execution
        context = {'executed_steps': []}
        
        # Execute pipeline
        await pipeline.execute(
            entity=entity,
            old_status="DRAFT",
            new_status="ACTIVE",
            actor=system_user,
            session=session,
            **context
        )
        
        # Verify all steps executed in order
        assert step1.executed
        assert step2.executed
        assert step3.executed
        assert step1.execution_order == 0
        assert step2.execution_order == 1
        assert step3.execution_order == 2
        assert context['executed_steps'] == ["step1", "step2", "step3"]
    
    @pytest.mark.asyncio
    async def test_pipeline_with_failing_step(self, session: AsyncSession, system_user: Player):
        """Test pipeline stops execution when a step fails"""
        # Create steps with one that fails
        step1 = RecordingStep("step1")
        step2 = RecordingStep("step2", should_fail=True)
        step3 = RecordingStep("step3")
        
        # Create pipeline
        pipeline = TransitionPipeline([step1, step2, step3])
        
        # Create entity
        entity = MockEntity()
        
        # Context to track execution
        context = {'executed_steps': []}
        
        # Execute pipeline - should raise exception
        with pytest.raises(RuntimeError, match="Step step2 failed"):
            await pipeline.execute(
                entity=entity,
                old_status="DRAFT",
                new_status="ACTIVE",
                actor=system_user,
                session=session,
                **context
            )
        
        # Verify execution stopped at failing step
        assert step1.executed
        assert step2.executed  # This one executed but failed
        assert not step3.executed  # This should not have executed
        assert context['executed_steps'] == ["step1", "step2"]
    
    @pytest.mark.asyncio
    async def test_pipeline_with_audit_context(self, session: AsyncSession, system_user: Player):
        """Test pipeline execution with audit context"""
        # Create steps
        auditing_step = AuditingStep()
        recording_step = RecordingStep("recording")
        
        # Create pipeline
        pipeline = TransitionPipeline([auditing_step, recording_step])
        
        # Create entity
        entity = MockEntity()
        
        # Execute with audit context
        async with AuditContext(session, entity_id=entity.id) as audit_context:
            await pipeline.execute(
                entity=entity,
                old_status="DRAFT",
                new_status="ACTIVE",
                actor=system_user,
                session=session,
                audit_context=audit_context
            )
            
            # Verify audit events were created
            assert len(audit_context.child_events) > 0
    
    @pytest.mark.asyncio
    async def test_pipeline_with_data_modification(self, session: AsyncSession, system_user: Player):
        """Test pipeline step that modifies entity data"""
        # Create steps
        modification_step = DataModificationStep()
        recording_step = RecordingStep("recording")
        
        # Create pipeline
        pipeline = TransitionPipeline([modification_step, recording_step])
        
        # Create entity
        entity = MockEntity()
        assert entity.metadata == {}
        
        # Execute pipeline
        await pipeline.execute(
            entity=entity,
            old_status="DRAFT", 
            new_status="ACTIVE",
            actor=system_user,
            session=session
        )
        
        # Verify entity was modified
        assert entity.metadata['modified_by_pipeline'] is True
        assert entity.metadata['transition'] == "DRAFT -> ACTIVE"
    
    @pytest.mark.asyncio
    async def test_empty_pipeline(self, session: AsyncSession, system_user: Player):
        """Test pipeline with no steps executes without error"""
        # Create empty pipeline
        pipeline = TransitionPipeline([])
        
        # Create entity
        entity = MockEntity()
        
        # Execute pipeline - should not raise any errors
        await pipeline.execute(
            entity=entity,
            old_status="DRAFT",
            new_status="ACTIVE",
            actor=system_user,
            session=session
        )
    
    @pytest.mark.asyncio
    async def test_pipeline_context_passing(self, session: AsyncSession, system_user: Player):
        """Test that context is properly passed between steps"""
        
        class ContextStep(TransitionStep):
            def __init__(self, name: str, key: str, value: any):
                self.name = name
                self.key = key
                self.value = value
            
            async def execute(self, entity, old_status, new_status, actor, session, audit_context=None, **context):
                # Add to context
                context[self.key] = self.value
                
                # Verify previous steps' context is available
                if self.name == "step2":
                    assert context.get('step1_data') == 'value1'
                elif self.name == "step3":
                    assert context.get('step1_data') == 'value1'
                    assert context.get('step2_data') == 'value2'
            
            @property
            def step_name(self):
                return self.name
        
        # Create steps that pass data through context
        step1 = ContextStep("step1", "step1_data", "value1")
        step2 = ContextStep("step2", "step2_data", "value2")
        step3 = ContextStep("step3", "step3_data", "value3")
        
        # Create pipeline
        pipeline = TransitionPipeline([step1, step2, step3])
        
        # Execute
        context = {}
        await pipeline.execute(
            entity=MockEntity(),
            old_status="DRAFT",
            new_status="ACTIVE",
            actor=system_user,
            session=session,
            **context
        )
        
        # Verify all context was preserved
        assert context['step1_data'] == 'value1'
        assert context['step2_data'] == 'value2'
        assert context['step3_data'] == 'value3'