from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlmodel import Column, Field

from utils.datetime import now_utc


def timestamp_column(
    nullable: bool = False, 
    default: Optional[Any] = None, 
    **kwargs
) -> Column:
    """
    Create a timezone-aware timestamp column.
    
    Args:
        nullable: Whether the column can be null
        default: Default value for the column
        **kwargs: Additional column arguments
        
    Returns:
        A SQLAlchemy Column configured with timezone-aware timestamp
    """
    return Column(
        TIMESTAMP(timezone=True),
        nullable=nullable,
        default=default or now_utc,
        **kwargs
    )


def created_at_field() -> Field:
    """Create a standardized created_at timestamp field."""
    return Field(
        sa_column=timestamp_column(default=now_utc),
        description="Time when the record was created"
    )


def updated_at_field() -> Field:
    """Create a standardized updated_at timestamp field."""
    return Field(
        sa_column=timestamp_column(default=now_utc, onupdate=now_utc),
        description="Time when the record was last updated"
    )