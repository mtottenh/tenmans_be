from datetime import datetime
from enum import Enum
from typing import Any, Optional, Type, TypeVar

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlmodel import Column, Field

from utils.datetime import now_utc


T = TypeVar('T', bound=Enum)


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


def enum_column(
    enum_class: Type[T],
    name: Optional[str] = None,
    **kwargs
) -> Column:
    """
    Create a properly configured Enum column for SQLModel classes.
    
    Args:
        enum_class: The Enum class to use
        name: Custom name for the enum type in the database (defaults to lowercase enum class name)
        **kwargs: Additional column arguments
    
    Returns:
        A SQLAlchemy Column configured for the enum
    """
    enum_name = name or enum_class.__name__.lower()
    return Column(
        sa.Enum(enum_class, name=enum_name),
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