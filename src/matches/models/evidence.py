# matches/models/evidence.py

from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from datetime import datetime
from enum import StrEnum
from typing import List, Optional
import uuid


class EvidenceStatus(StrEnum):
    """Status of match evidence"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class MatchEvidence(SQLModel, table=True):
    """Records demo files and other evidence for matches"""
    __tablename__ = "match_evidence"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    fixture_id: uuid.UUID = Field(sa_column=Column(ForeignKey("fixtures.id")))
    match_number: int  # For BO3/BO5
    demo_url: str
    stats_url: Optional[str] = None
    upload_type: str  # "manual", "automatic"
    status: EvidenceStatus = Field(
        sa_column=Column(Enum(EvidenceStatus)),
        default=EvidenceStatus.PENDING
    )
    submitted_by: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))
    submitted_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    # Relationships
    fixture: "Fixture" = Relationship(back_populates="evidence")
    submitter: "Player" = Relationship(back_populates="submitted_evidence")
    confirmations: List["EvidenceConfirmation"] = Relationship(back_populates="evidence")


class EvidenceConfirmation(SQLModel, table=True):
    """Tracks confirmation status of match evidence"""
    __tablename__ = "evidence_confirmations"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4)
    )
    evidence_id: uuid.UUID = Field(sa_column=Column(ForeignKey("match_evidence.id")))
    confirmed_by: uuid.UUID = Field(sa_column=Column(ForeignKey("players.id")))
    team_id: uuid.UUID = Field(sa_column=Column(ForeignKey("teams.id")))
    status: str  # "confirmed", "disputed"
    notes: Optional[str] = None
    confirmed_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    # Relationships
    evidence: MatchEvidence = Relationship(back_populates="confirmations")
    confirmer: "Player" = Relationship(back_populates="evidence_confirmations")
    team: "Team" = Relationship(back_populates="evidence_confirmations")