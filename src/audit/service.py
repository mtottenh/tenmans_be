from functools import wraps
from typing import Any, Callable, Dict, Optional
from sqlmodel.ext.asyncio.session import AsyncSession
from audit.models import AuditLog
from auth.models import Player
from sqlmodel import select, desc
import inspect
import uuid
from datetime import datetime

class AuditService:
    """Service for handling audit logging"""
    
    @staticmethod
    def audited_transaction(
        action_type: str,
        entity_type: str,
        details_extractor: Optional[Callable] = None
    ):
        """
        Decorator for auditing database transactions.
        
        Args:
            action_type: Type of action being performed (e.g., "team_create")
            entity_type: Type of entity being affected (e.g., "team")
            details_extractor: Optional function to extract audit details from the result
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Get session and actor from args/kwargs
                session = next((arg for arg in args if isinstance(arg, AsyncSession)), kwargs.get('session'))
                actor = next((arg for arg in args if isinstance(arg, Player)), kwargs.get('actor'))
                
                if not session or not actor:
                    # Get parameter names from function signature
                    sig = inspect.signature(func)
                    param_names = list(sig.parameters.keys())
                    
                    # Try to get session and actor from named parameters
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
                    
                    # Get entity_id and details
                    entity_id = getattr(result, 'id', None)
                    
                    # Extract details using provided function or default to basic details
                    if details_extractor:
                        details = details_extractor(result)
                    else:
                        details = {
                            "result_type": type(result).__name__,
                            "result_str": str(result)
                        }
                    
                    # Create audit log
                    audit_log = AuditLog(
                        action_type=action_type,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        actor_id=actor.uid,
                        details=details,
                        created_at=datetime.now()
                    )
                    session.add(audit_log)
                    
                    # Commit the transaction
                    await session.commit()
                    
                    # Refresh the result if it's a model
                    if hasattr(result, '__table__'):
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
    ) -> list[AuditLog]:
        """Retrieves audit logs for a specific entity"""
        stmt = select(AuditLog).where(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id
        ).order_by(desc(AuditLog.created_at))
        result = await session.exec(stmt)
        return result.all()