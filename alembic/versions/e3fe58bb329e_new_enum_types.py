"""New_Enum_Types

Revision ID: e3fe58bb329e
Revises: 72714e929344
Create Date: 2025-05-20 12:34:31.394020

"""


from typing import Sequence, Union, Type, List, Set
import enum
import sys
import os
import sqlmodel
# Add the project root to the path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector

# Import your actual enum classes
from competitions.base_schemas import MapCategory, GameMode, TournamentState, LeagueFormat, MapSelectionMethod
from moderation.models import ModerationActionType
from competitions.models.scheduling import AvailabilityType, AvailabilityStatus
from competitions.map_pool.schemas import MapPoolSelectionType, MapPoolStatus
from competitions.models.lobby import VetoActionType
from matches.evidence.models import EvidenceStatus
from matches.models import DisputeStatus
# revision identifiers, used by Alembic.
revision: str = 'e3fe58bb329e'
down_revision: Union[str, None] = '72714e929344'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def get_enum_values(inspector: Inspector, name: str) -> Set[str]:
    """Get existing enum values from the database"""
    existing_enums = inspector.get_enums()
    for enum_info in existing_enums:
        if enum_info['name'] == name:
            return set(enum_info['labels'])
    return set()


def create_or_update_enum(enum_class: Type[enum.Enum], db_name: str) -> List[str]:
    """
    Create enum if it doesn't exist, or update it by adding missing values
    Returns list of values that were added
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    code_values = {e.name for e in enum_class}

    # Check if enum exists
    existing_values = get_enum_values(inspector, db_name)
    added_values = []

    if not existing_values:
        # Enum doesn't exist, create it
        enum_type = sa.Enum(*code_values, name=db_name)
        enum_type.create(conn)
        added_values = list(code_values)
        print(f"Created enum '{db_name}' with values: {', '.join(added_values)}")
    else:
        # Enum exists, add missing values
        missing_values = code_values - existing_values
        for value in missing_values:
            # Safely quote the value to prevent SQL injection
            safe_value = value.replace("'", "''")
            op.execute(f"ALTER TYPE {db_name} ADD VALUE IF NOT EXISTS '{safe_value}'")
            added_values.append(value)
            print(f"Added value '{value}' to enum '{db_name}'")

    return added_values


def upgrade() -> None:
    # Map enum_class to database enum name
    enum_mappings = {
        MapCategory: 'mapcategory',
        ModerationActionType: 'moderationactiontype',
        AvailabilityType: 'availabilitytype',
        AvailabilityStatus: 'availabilitystatus',
        MapPoolSelectionType: 'mappoolselectiontype',
        MapPoolStatus: 'mappoolstatus',
        VetoActionType: 'vetoactiontype',
        EvidenceStatus: 'evidencestatus',
        DisputeStatus: 'disputestatus',
        TournamentState: 'tournamentstate',
        GameMode: 'gamemode',
        LeagueFormat: 'leagueformat',
        MapSelectionMethod: 'mapselectionmethod'
    }

    # Create or update all enum types
    changes = {}
    for enum_class, db_name in enum_mappings.items():
        added_values = create_or_update_enum(enum_class, db_name)
        if added_values:
            changes[db_name] = added_values

    # Record what changes were made in this migration
    if changes:
        comment = f"Enum updates in migration {revision}:\n"
        for enum_name, values in changes.items():
            if values:
                comment += f"- Added to {enum_name}: {', '.join(values)}\n"

        op.execute(f"COMMENT ON SCHEMA public IS '{comment}'")


def downgrade() -> None:
    """
    Downgrade can't remove enum values in PostgreSQL, but we can
    report which enums were created entirely by this migration.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Map enum_class to database enum name
    enum_mappings = {
        MapCategory: 'mapcategory',
        ModerationActionType: 'moderationactiontype',
        AvailabilityType: 'availabilitytype',
        AvailabilityStatus: 'availabilitystatus',
        MapPoolSelectionType: 'mappoolselectiontype',
        MapPoolStatus: 'mappoolstatus',
        VetoActionType: 'vetoactiontype',
        EvidenceStatus: 'evidencestatus',
        DisputeStatus: 'disputestatus',
        GameMode: 'gamemode',
        LeagueFormat: 'leagueformat',
        MapSelectionMethod: 'mapselectionmethod'
    }

    # List enums that might be safe to drop (not used by any table)
    for db_name in enum_mappings.values():
        # Check if enum is used by any column
        result = conn.execute(sa.text("""
            SELECT 1
            FROM pg_catalog.pg_type t
            JOIN pg_catalog.pg_enum e ON t.oid = e.enumtypid
            JOIN pg_catalog.pg_depend d ON t.oid = d.refobjid
            WHERE t.typname = :typename AND d.deptype = 'n'
        """), {"typename": db_name}).fetchone()

        if not result:
            # No dependencies found, we could drop it safely
            print(f"Enum '{db_name}' is not used by any column and could be dropped.")

    print("\nNOTE: PostgreSQL doesn't support removing enum values.")
    print("Values added in this migration will still exist in the database.")
    print("If you need to completely remove an enum type, ensure no tables reference it.")
