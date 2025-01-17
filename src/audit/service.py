from functools import wraps
from typing import Any, Callable, Dict, Optional
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession
from audit.models import AuditLog
from auth.models import Player
import inspect
from datetime import datetime
import uuid
from typing import List


class AuditService:
    @staticmethod
    def audited_transaction(
        action_type: str,
        entity_type: str,
        details_extractor: Optional[Callable] = None
    ):
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Get session and actor from args/kwargs
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
                
                if not session or not actor:
                    raise ValueError("audited_transaction requires session and actor parameters")
                
                try:
                    # Execute the wrapped function
                    result = await func(*args, **kwargs)
                    
                    # First phase: Commit the main resource
                    await session.commit()
                    
                    # Refresh to get generated IDs
                    if hasattr(result, '__table__'):
                        await session.refresh(result)
                    
                    # Get entity_id and details after refresh
                    entity_id = getattr(result, 'id', None)
                    
                    # Extract details using provided function
                    details: Dict[str, Any]
                    if details_extractor:
                        instance = args[0] if args else None
                        
                        if instance and not isinstance(details_extractor, staticmethod):
                            bound_extractor = details_extractor.__get__(instance, type(instance))
                            details = bound_extractor(result)
                        else:
                            details = details_extractor(result)
                    else:
                        details = {
                            "result_type": type(result).__name__,
                            "result_str": str(result)
                        }
                    await session.refresh(actor)
                    # Second phase: Create and commit audit log
                    audit_log = AuditLog(
                        action_type=action_type,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        actor_id=actor.uid,
                        details=details,
                        created_at=datetime.now()
                    )
                    session.add(audit_log)
                    await session.commit()
                    await session.refresh(result)
                    return result
                    
                except Exception as e:
                    await session.rollback()
                    raise
                    
            return wrapper
        return decorator

    async def get_entity_audit_logs(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        session: AsyncSession
    ) -> List[AuditLog]:
        stmt = select(AuditLog).where(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id
        ).order_by(desc(AuditLog.created_at))
        result = await session.execute(stmt)
        return result.all()