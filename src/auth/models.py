from sqlmodel import SQLModel, Field, Column, Relationship
import sqlalchemy.dialects.sqlite as sl
from sqlalchemy import ForeignKey
from sqlalchemy_utils import UUIDType
from datetime import datetime
from enum import StrEnum
import uuid
from typing import List, Optional

class AuthType(StrEnum):
    STEAM = "steam"
    EMAIL = "email"


class Role(SQLModel, table=True):
    __tablename__ = "roles"
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True)
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    permissions: List["Permission"] = Relationship(
        back_populates="roles",
        link_model="RolePermission"
    )

class Permission(SQLModel, table=True):
    __tablename__ = "permissions"
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(unique=True)
    description: str
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    roles: List[Role] = Relationship(
        back_populates="permissions",
        link_model="RolePermission"
    )

class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"
    role_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("roles.id"), primary_key=True)
    )
    permission_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("permissions.id"), primary_key=True)
    )

class PlayerRole(SQLModel, table=True):
    __tablename__ = "player_roles"
    player_uid: uuid.UUID = Field(
        sa_column=Column(ForeignKey("players.uid"), primary_key=True)
    )
    role_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("roles.id"), primary_key=True)
    )
    scope_type: str  # 'global', 'team', 'tournament'
    scope_id: Optional[uuid.UUID] = Field(default=None)
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Player(SQLModel, table=True):
    __tablename__ = "players"

    uid: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    name: str
    steam_id: str = Field(unique=True)  # Required for all users
    email: Optional[str] = Field(unique=True, nullable=True)  # Optional for Steam users
    auth_type: AuthType
    password_hash: Optional[str] = Field(nullable=True)  # Optional for Steam users
    current_elo: Optional[int]
    highest_elo: Optional[int]
    verification_status: VerificationStatus = Field(default=VerificationStatus.PENDING)
    verified_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.uid"), nullable=True))
    verification_notes: Optional[str]
    verification_date: Optional[datetime]
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    
    roles: List["Role"] = Relationship(
        back_populates="players",
        link_model="PlayerRole"
    )
    team_rosters: List["Roster"] = Relationship(back_populates="player")
    match_participations: List["MatchPlayer"] = Relationship(back_populates="player")
    captain_of: List["TeamCaptain"] = Relationship(back_populates="player")

class VerificationRequest(SQLModel, table=True):
    __tablename__ = "verification_requests"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUIDType, nullable=False, primary_key=True, default=uuid.uuid4)
    )
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    admin_notes: Optional[str]
    submitted_evidence: Optional[str]  # Could store URLs or references to evidence
    status: VerificationStatus = Field(default=VerificationStatus.PENDING)
    created_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(sl.TIMESTAMP, default=datetime.now))

    player: Player = Relationship(back_populates="verification_requests")
