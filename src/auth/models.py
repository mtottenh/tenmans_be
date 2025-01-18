from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import StrEnum
import uuid
from typing import List, Optional
from audit.models import AuditEvent
from moderation.models import Ban
from substitutes.models import SubstituteAvailability
from teams.join_request.models import TeamJoinRequest
class AuthType(StrEnum):
    STEAM = "steam"
    EMAIL = "email"

class RolePermission(SQLModel, AsyncAttrs, table=True):
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
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))


class Role(SQLModel, AsyncAttrs, table=True):
    __tablename__ = "roles"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True),  primary_key=True, nullable=False, default=uuid.uuid4))
    name: str = Field(unique=True)
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    permissions: List["Permission"] = Relationship(
        back_populates="roles",
        link_model=RolePermission
    )
    players: List["Player"] = Relationship(
        back_populates="roles",  # You should define a `roles` field in `Player`
        link_model=PlayerRole
    )
class Permission(SQLModel, AsyncAttrs, table=True):
    __tablename__ = "permissions"
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True),primary_key=True,nullable=False, default=uuid.uuid4) )
    name: str = Field(unique=True)
    description: str
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    roles: List[Role] = Relationship(
        back_populates="permissions",
        link_model=RolePermission
    )



class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Player(SQLModel, AsyncAttrs, table=True):
    __tablename__ = "players"

    uid: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True),  primary_key=True,  nullable=False, default=uuid.uuid4))
    name: str
    steam_id: str = Field(unique=True)  # Required for all users
    # discord_info: 
    email: Optional[str] = Field(unique=True, nullable=True)  # Optional for Steam users
    auth_type: AuthType
    password_hash: Optional[str] = Field(nullable=True)  # Optional for Steam users
    current_elo: Optional[int]
    highest_elo: Optional[int]
    verification_status: VerificationStatus = Field(default=VerificationStatus.PENDING)
    verified_by: Optional[uuid.UUID] = Field(sa_column=Column(ForeignKey("players.uid"), nullable=True))
    verification_notes: Optional[str]
    verification_date: Optional[datetime]
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    
    roles: List["Role"] = Relationship(
        back_populates="players", 
        link_model=PlayerRole
    )
    team_rosters: List["Roster"] = Relationship(back_populates="player")
    match_participations: List["MatchPlayer"] = Relationship(back_populates="player")
    captain_of: List["TeamCaptain"] = Relationship(back_populates="player")
    pug_participations: List["PugPlayer"] = Relationship(back_populates="player")
    pug_captain_of: List["PugTeam"] = Relationship(back_populates="captain")
    created_pugs: List["Pug"] = Relationship(back_populates="creator")
    bans: List[Ban] = Relationship(back_populates="player",  sa_relationship_kwargs={"primaryjoin": "Ban.player_uid == Player.uid"})
    issued_bans: List[Ban] = Relationship(
        back_populates="admin",
        sa_relationship=relationship(Ban, back_populates="admin", foreign_keys="Ban.issued_by")
    )
    substitute_availability: List["SubstituteAvailability"] = Relationship(
        back_populates="player"
    )
    join_requests: List[TeamJoinRequest] = Relationship(
        back_populates="player",
        sa_relationship_kwargs={"foreign_keys": "TeamJoinRequest.player_uid"}
    )
    handled_join_requests: List[TeamJoinRequest] = Relationship(
        back_populates="responder",
        sa_relationship_kwargs={"foreign_keys": "TeamJoinRequest.responded_by"}
    )
    verification_requests: "VerificationRequest" = Relationship(back_populates="player")
    tournament_registration_requests: List["TournamentRegistration"] = Relationship(back_populates="requester",  sa_relationship_kwargs={"primaryjoin": "Player.uid == TournamentRegistration.requested_by"})
    tournament_registration_reviews: List["TournamentRegistration"] = Relationship(back_populates="reviewer",  sa_relationship_kwargs={"primaryjoin": "Player.uid == TournamentRegistration.reviewed_by"})
    submitted_results: List["Result"] = Relationship(back_populates="submitter", sa_relationship_kwargs={"primaryjoin": "Result.submitted_by == Player.uid"})
    confirmed_results: List["Result"] = Relationship(back_populates="confirmer", sa_relationship_kwargs={"primaryjoin": "Result.confirmed_by == Player.uid"})
    admin_overridden_results: List["Result"] = Relationship(back_populates="admin_overrider",  sa_relationship_kwargs={"primaryjoin": "Result.admin_override_by == Player.uid"})
    audit_events: List[AuditEvent] = Relationship(back_populates="actor")
    revoked_bans: List[Ban] = Relationship(back_populates="revoking_admin",
                     sa_relationship=relationship(Ban, back_populates="revoking_admin", foreign_keys="Ban.revoked_by")                        
                                             
                                             )


class VerificationRequest(SQLModel, AsyncAttrs, table=True):
    __tablename__ = "verification_requests"
    
    id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True),  primary_key=True,  nullable=False, default=uuid.uuid4))
    player_uid: uuid.UUID = Field(sa_column=Column(ForeignKey("players.uid")))
    admin_notes: Optional[str]
    submitted_evidence: Optional[str]  # Could store URLs or references to evidence
    status: VerificationStatus = Field(default=VerificationStatus.PENDING)
    created_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP, default=datetime.now))

    player: Player = Relationship(back_populates="verification_requests")
