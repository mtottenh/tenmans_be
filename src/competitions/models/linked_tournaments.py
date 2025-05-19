import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSON, TIMESTAMP, UUID
from sqlmodel import Column, Field, Relationship, SQLModel


if TYPE_CHECKING:
    from competitions.models.tournaments import Tournament



class LinkedTournament(SQLModel, table=True):
    """Links tournaments for progression (e.g., league to knockout)"""

    __tablename__ = "linked_tournaments"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
        )
    )
    source_tournament_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tournaments.id"))
    )  # League
    target_tournament_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tournaments.id"))
    )  # Knockout

    qualification_rules: dict[str, Any] = Field(
        sa_column=Column(JSON),
        default={
            "qualify_top": 8,  # Default to top 8 teams
            "tiebreaker_rules": [
                "head_to_head",
                "round_difference",
                "total_rounds_won",
            ],
        },
    )

    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    # Relationships
    source_tournament: "Tournament" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[LinkedTournament.source_tournament_id]"
        }
    )
    target_tournament: "Tournament" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[LinkedTournament.target_tournament_id]"
        }
    )
