from functools import wraps, partial
from typing import Any, Callable, Dict, List, Optional, TypeVar, Tuple
from sqlalchemy import func
from sqlmodel import and_, select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime, timedelta
import inspect
import uuid
import logging

from audit.context import AuditContext
from auth.models import Player
# Somehow the below is required because of the weird Relationships
from competitions.models.tournaments import Tournament 
from audit.schemas import  AuditEventType, AuditEventState
from audit.models import AuditEvent

LOG = logging.getLogger(__name__)
T = TypeVar('T')


class AuditQueryResult:
    """Container for audit query results with optional statistics"""
    def __init__(
        self,
        events: List[AuditEvent],
        total_count: int,
        statistics: Optional[Dict] = None
    ):
        self.events = events
        self.total_count = total_count
        self.statistics = statistics or {}


class AuditService:
    """Enhanced audit service with support for cascading, and status tracking"""

    @staticmethod
    def _get_session_and_actor(args: tuple, kwargs: dict, func: Callable) -> Tuple[Optional[AsyncSession], Optional[Player]]:
        """Extract session and actor from function arguments"""
        session = next((arg for arg in args if isinstance(arg, AsyncSession)), kwargs.get('session'))
        actor = next((arg for arg in args if isinstance(arg, Player)), kwargs.get('actor'))
        
        if not session or not actor:
            sig = inspect.signature(func)
            param_names = list(sig.parameters.keys())
            
            if not session:
                session_idx = param_names.index('session')
                if session_idx < len(args):
                    session = args[session_idx]
            if not actor:
                actor_idx = param_names.index('actor')
                if actor_idx < len(args):
                    actor = args[actor_idx]
                    
        return session, actor
    
    @staticmethod
    def _extract_details(
        details_extractor: Optional[Callable],
        instance: Any,
        result: Any,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract details using bound or unbound methods"""
        if details_extractor is None:
            return {
                "result_type": type(result).__name__,
                "result_str": str(result)
            }

        if inspect.ismethod(details_extractor):
            # Already bound method
            return details_extractor(result, context)
        else:
            # Unbound method - bind it to the instance
            bound_method = partial(details_extractor, instance)
            return bound_method(result, context)

    @staticmethod
    def _extract_id(
        id_extractor: Optional[Callable],
        instance: Any,
        entity: Any
    ) -> uuid.UUID:
        """Extract entity ID using bound or unbound methods"""
        if hasattr(entity, 'id'):
            return entity.id

        if id_extractor is None:
            # Generate a UUID if no ID extractor is provided
            return uuid.uuid4()

        if inspect.ismethod(id_extractor):
            # Already bound method
            return id_extractor(entity)
        else:
            # Unbound method - bind it to the instance
            bound_method = partial(id_extractor, instance)
            return bound_method(entity)



    async def query_events(
        self,
        session: AsyncSession,
        action_type: Optional[AuditEventType] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_details: bool = True,
        offset: int = 0,
        limit: Optional[int] = 100,
        calculate_stats: bool = False
    ) -> AuditQueryResult:
        """
        Query audit events with comprehensive filtering options
        
        Args:
            session: Database session
            action_type: Filter by specific action type
            entity_type: Filter by entity type
            entity_id: Filter by specific entity ID
            actor_id: Filter by actor ID
            start_date: Include events after this date
            end_date: Include events before this date
            include_details: Whether to include full event details
            offset: Number of records to skip
            limit: Maximum number of records to return
            calculate_stats: Whether to calculate additional statistics
            
        Returns:
            AuditQueryResult containing events and optional statistics
        """
        # Build base query
        query = select(AuditEvent)
        
        # Apply filters
        conditions = []
        if action_type:
            conditions.append(AuditEvent.action_type == action_type)
        if entity_type:
            conditions.append(AuditEvent.entity_type == entity_type)
        if entity_id:
            conditions.append(AuditEvent.entity_id == entity_id)
        if actor_id:
            conditions.append(AuditEvent.actor_id == actor_id)
        if start_date:
            conditions.append(AuditEvent.timestamp >= start_date)
        if end_date:
            conditions.append(AuditEvent.timestamp <= end_date)
            
        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(query)
        total_count = (await session.execute(count_query)).scalar()

        # Apply pagination
        query = query.order_by(AuditEvent.timestamp.desc())
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        # Execute main query
        result = await session.execute(query)
        events = result.scalars().all()

        # Calculate statistics if requested
        statistics = None
        if calculate_stats:
            statistics = await self._calculate_query_statistics(
                session, conditions, start_date, end_date
            )

        return AuditQueryResult(events, total_count, statistics)

    async def get_summary_statistics(
        self,
        session: AsyncSession,
        days: int = 7,
        entity_type: Optional[str] = None
    ) -> Dict:
        """
        Get summary statistics for audit events
        
        Args:
            session: Database session
            days: Number of days to include in summary
            entity_type: Optional filter for specific entity type
            
        Returns:
            Dictionary containing various statistics
        """
        start_date = datetime.now() - timedelta(days=days)
        
        # Base query conditions
        conditions = [AuditEvent.timestamp >= start_date]
        if entity_type:
            conditions.append(AuditEvent.entity_type == entity_type)
            
        # Get action type counts
        action_query = select(
            AuditEvent.action_type,
            func.count(AuditEvent.id).label('count')
        ).where(
            and_(*conditions)
        ).group_by(
            AuditEvent.action_type
        )
        
        action_result = await session.execute(action_query)
        action_counts = {
            action_type: count
            for action_type, count in action_result.scalars().all()
        }
        
        # Get entity type counts
        entity_query = select(
            AuditEvent.entity_type,
            func.count(AuditEvent.id).label('count')
        ).where(
            and_(*conditions)
        ).group_by(
            AuditEvent.entity_type
        )
        
        entity_result = await session.execute(entity_query)
        entity_counts = {
            entity_type: count
            for entity_type, count in entity_result.scalars().all()
        }
        
        # Get actor counts
        actor_query = select(
            AuditEvent.actor_id,
            func.count(AuditEvent.id).label('count')
        ).where(
            and_(*conditions)
        ).group_by(
            AuditEvent.actor_id
        ).order_by(
            func.count(AuditEvent.id).desc()
        ).limit(10)
        
        actor_result = await session.execute(actor_query)
        top_actors = {
            str(actor_id): count
            for actor_id, count in actor_result.scalars().all()
        }
        
        return {
            "period_days": days,
            "total_events": sum(action_counts.values()),
            "action_counts": action_counts,
            "entity_counts": entity_counts,
            "top_actors": top_actors
        }

    async def get_entity_history(
        self,
        session: AsyncSession,
        entity_type: str,
        entity_id: str,
        include_cascaded: bool = True
    ) -> List[AuditEvent]:
        """
        Get complete audit history for an entity
        
        Args:
            session: Database session
            entity_type: Type of entity
            entity_id: Entity ID
            include_cascaded: Whether to include cascaded events
            
        Returns:
            List of audit events ordered by timestamp
        """
        if include_cascaded:
            # Get root events and their cascaded events
            root_events = await self.get_audit_trail(
                entity_type=entity_type,
                entity_id=entity_id,
                session=session,
                include_cascaded=True
            )
            return root_events
        else:
            # Get direct events only
            query = select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == entity_type,
                    AuditEvent.entity_id == entity_id
                )
            ).order_by(AuditEvent.timestamp)
            
            result = await session.execute(query)
            return result.scalars().all()

    async def _calculate_query_statistics(
        self,
        session: AsyncSession,
        base_conditions: List,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> Dict:
        """Calculate additional statistics for a query"""
        conditions = base_conditions.copy()
        
        # Calculate event distribution over time
        time_query = select(
            func.date_trunc('day', AuditEvent.timestamp),
            func.count()
        ).where(
            and_(*conditions)
        ).group_by(
            func.date_trunc('day', AuditEvent.timestamp)
        ).order_by(
            func.date_trunc('day', AuditEvent.timestamp)
        )
        
        time_result = await session.execute(time_query)
        time_distribution = {
            date.strftime('%Y-%m-%d'): count
            for date, count in time_result.scalars().all()
        }
        
        return {
            "time_distribution": time_distribution,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            }
        }

    async def get_audit_trail(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        session: AsyncSession,
        include_cascaded: bool = False,
        include_details: bool = True
    ) -> List[Dict[str, Any]]:
        """Get audit trail for an entity, optionally including cascaded events"""
        if include_cascaded:
            # Get root events for the entity
            stmt = select(AuditEvent).where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
                AuditEvent.parent_event_id.is_(None)
            )
            root_events = (await session.execute(stmt)).scalars().all()
            
            # Get all related events
            all_events = []
            for event in root_events:
                stmt = select(AuditEvent).where(
                    AuditEvent.root_event_id == event.id
                ).order_by(
                    AuditEvent.sequence_number,
                    desc(AuditEvent.timestamp)
                )
                related_events = (await session.execute(stmt)).scalars().all()
                all_events.extend(related_events)
            
            return [
                self._format_audit_event(event, include_details)
                for event in all_events
            ]
        else:
            stmt = select(AuditEvent).where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id
            ).order_by(desc(AuditEvent.timestamp))
            
            events = (await session.execute(stmt)).scalars().all()
            return [
                self._format_audit_event(event, include_details)
                for event in events
           ]

    def _format_audit_event(self, event: AuditEvent, include_details: bool) -> Dict[str, Any]:
        """Format an audit event for response"""
        formatted = {
            "id": event.id,
            "action_type": event.action_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "actor_id": event.actor_id,
            "timestamp": event.timestamp,
            "event_state": event.event_state
        }

        if event.action_type == AuditEventType.STATUS_CHANGE:
            formatted.update({
                "previous_status": event.previous_status,
                "new_status": event.new_status,
                "transition_reason": event.transition_reason
            })

        if event.action_type == AuditEventType.BULK_OPERATION:
            formatted.update({
                "operation_count": event.operation_count,
                "affected_entities": event.affected_entities
            })

        if event.scope_type:
            formatted.update({
                "scope_type": event.scope_type,
                "scope_id": event.scope_id
            })

        if include_details:
            formatted["details"] = event.details
            if event.error_message:
                formatted["error"] = {
                    "message": event.error_message,
                    "details": event.error_details
                }

        return formatted

    async def get_grace_period_events(
        self,
        session: AsyncSession,
        entity_type: Optional[str] = None
    ) -> List[AuditEvent]:
        """Get audit events that are still within their grace period"""
        now = datetime.now()
        stmt = select(AuditEvent).where(
            AuditEvent.grace_period_end.is_not(None),
            AuditEvent.grace_period_end > now
        )
        
        if entity_type:
            stmt = stmt.where(AuditEvent.entity_type == entity_type)
            
        return (await session.execute(stmt)).scalars().all()


    
    @classmethod
    def audited_transaction(
        cls,
        action_type: AuditEventType,
        entity_type: str,
        details_extractor: Optional[Callable] = None,
        id_extractor: Optional[Callable] = None,
        scope_type: Optional[str] = None,
        grace_period: Optional[timedelta] = None
    ):
        """Decorator for auditing create/update transactions"""
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def wrapper(self, *args, **kwargs) -> T:
                session, actor = cls._get_session_and_actor(args, kwargs, func)
                audit_service = cls()
                if not session or not actor:
                    raise ValueError("Session and actor are required for audited transactions")

                
                # Extract entity and ID based on operation type
                entity_id = None
                entity  = None
                pre_execution_details = None

                # TODO - This will have us default to the first entity that's a SQLModel
                # Being the one that is stuck in the audit log.
                # We need to be *very* Careful when using this decorator that 
                # Decorated functions pass parameters in the correct order if this is the case.
                # For DELETE and UPDATE, we need entity details before the operation
                if action_type in [AuditEventType.DELETE, AuditEventType.UPDATE]:
                    entity = next((arg for arg in args if hasattr(arg, '__table__')), None)
                    if not entity:
                        raise ValueError("Entity required for delete/update operations")
                    context = {'actor': actor, **kwargs}
                    pre_execution_details = cls._extract_details(details_extractor, self, entity, context)
                    entity_id = cls._extract_id(id_extractor, self, entity)


                # Check if an AuditContext exists, either from kwargs or an existing context
                audit_context: Optional[AuditContext] = kwargs.get('audit_context', None)
                result = None
                # If no context exists, create a new one
                if audit_context is None:
                    async with AuditContext(session, entity_id=entity_id) as audit_context:
                        kwargs['audit_context'] = audit_context
                        if not audit_context.root_event:
                            # TODO - uuid() - we should probaly try to use the UUID of entities that already exist
                            # We can't for entities that are being breated through.
                            await audit_context.create_root_event(action_type, entity_type, actor, "Root Event")
                        result = await func(self, *args, **kwargs)
                        await session.flush()
                        await session.refresh(result)
                        await session.refresh(actor)
                        if action_type == AuditEventType.DELETE:
                            await audit_context.create_audit_event(
                                session=session,
                                action_type=action_type,
                                entity_type=entity_type,
                                entity_id=entity_id,
                                actor=actor,
                                details=pre_execution_details,
                                grace_period=grace_period
                            )
                        else:
                            entity_id = cls._extract_id(id_extractor, None, result)
                            if action_type == AuditEventType.CREATE:
                                if entity_id and audit_context.root_event:
                                    # Update the root event's entity_id if it was null
                                    # update_root_event_entity_id ensures that it only ever updates
                                    # once with the outer-most event's entity_id
                                    await audit_context.update_root_event_entity_id(entity_id)
                            context_data = {
                                'actor': actor,
                                'result': result,
                                **kwargs
                            }
                            details = cls._extract_details(details_extractor, None, result, context_data)
                            await audit_context.create_audit_event(
                                session=session,
                                action_type=action_type,
                                entity_type=entity_type,
                                entity_id=entity_id,
                                actor=actor,
                                details=details,
                                grace_period=grace_period,
                                scope_type=scope_type,
                                scope_id=kwargs.get('scope_id')
                            )
                        

                else:
                    result = await func(self, *args, **kwargs)
                    await session.flush()
                    await session.refresh(result)
                    await session.refresh(actor)
                    if action_type == AuditEventType.DELETE:
                        await audit_context.create_audit_event(
                            session=session,
                            action_type=action_type,
                            entity_type=entity_type,
                            entity_id=entity_id,
                            actor=actor,
                            details=pre_execution_details,
                            grace_period=grace_period
                        )
                    else:
                        entity_id = cls._extract_id(id_extractor, None, result)
                        if action_type == AuditEventType.CREATE:
                            if entity_id and audit_context.root_event:
                                # Update the root event's entity_id if it was null
                                # update_root_event_entity_id ensures that it only ever updates
                                # once with the outer-most event's entity_id
                                await audit_context.update_root_event_entity_id(entity_id)
                        context_data = {
                            'actor': actor,
                            'result': result,
                            **kwargs
                        }
                        details = cls._extract_details(details_extractor, None, result, context_data)
                        await audit_context.create_audit_event(
                            session=session,
                            action_type=action_type,
                            entity_type=entity_type,
                            entity_id=entity_id,
                            actor=actor,
                            details=details,
                            grace_period=grace_period,
                            scope_type=scope_type,
                            scope_id=kwargs.get('scope_id')
                        )
                await session.refresh(result) 
                return result

            return wrapper
        return decorator


def create_audit_service() -> AuditService:
    return AuditService()