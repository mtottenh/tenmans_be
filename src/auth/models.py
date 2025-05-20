import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlmodel import Column, Field, Relationship, SQLModel

from db.models import created_at_field, timestamp_column, updated_at_field
from utils.datetime import now_utc

from audit.models import AuditEvent
from auth.schemas import AuthType, PlayerStatus
from competitions.models.scheduling import PlayerAvailability
from moderation.models import Ban, ModerationAction
from substitutes.models import SubstituteAvailability
from teams.join_request.models import TeamJoinRequest


if TYPE_CHECKING:
    from auth.models import Player
    from competitions.models.tournaments import TournamentRegistration
    from matches.evidence.models import EvidenceConfirmation, MatchEvidence
    from matches.models import MatchPlayer, Result
    from pugs.models import Pug, PugPlayer, PugTeam
    from teams.models import Roster, TeamCaptain



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
    player_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("players.id"), primary_key=True)
    )
    role_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("roles.id"), primary_key=True)
    )
    scope_type: str  # 'global', 'team', 'tournament'
    scope_id: Optional[uuid.UUID] = Field(default=None)
    created_at: datetime = created_at_field()


class Role(SQLModel, table=True):
    __tablename__ = "roles"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
        )
    )
    name: str = Field(unique=True)
    created_at: datetime = created_at_field()
    permissions: list["Permission"] = Relationship(
        back_populates="roles", link_model=RolePermission
    )
    players: list["Player"] = Relationship(
        back_populates="roles",  # You should define a `roles` field in `Player`
        link_model=PlayerRole,
    )


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"
    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
        )
    )
    name: str = Field(unique=True)
    description: str
    created_at: datetime = created_at_field()
    roles: list[Role] = Relationship(
        back_populates="permissions", link_model=RolePermission
    )


class Player(SQLModel, table=True):
    __tablename__ = "players"

    id: uuid.UUID = Field(
        sa_column=Column(
            UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
        )
    )
    name: str
    steam_id: str = Field(unique=True)  # Required for all users
    email: Optional[str] = Field(unique=True, nullable=True)  # Optional for Steam users
    auth_type: AuthType
    password_hash: Optional[str] = Field(nullable=True)  # Optional for Steam users
    current_elo: Optional[int]
    highest_elo: Optional[int]

    # Verification    - TODO,  can this live in the audit log?
    verification_evidence: Optional[str]  # Could be a URL to a profile link etc.

    # Status field
    status: PlayerStatus = Field(default=PlayerStatus.PENDING_VERIFICATION)

    # Timestamps
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    # Special AuditService Relation
    audit_events: list[AuditEvent] = Relationship(back_populates="actor")

    # Existing Relations
    roles: list["Role"] = Relationship(back_populates="players", link_model=PlayerRole)
    team_rosters: list["Roster"] = Relationship(back_populates="player")
    captain_of: list["TeamCaptain"] = Relationship(back_populates="player")
    join_requests: list[TeamJoinRequest] = Relationship(
        back_populates="player",
        sa_relationship_kwargs={"foreign_keys": "TeamJoinRequest.player_id"},
    )
    handled_join_requests: list[TeamJoinRequest] = Relationship(
        back_populates="responder",
        sa_relationship_kwargs={"foreign_keys": "TeamJoinRequest.responded_by"},
    )
    match_participations: list["MatchPlayer"] = Relationship(back_populates="player")
    substitute_availability: list["SubstituteAvailability"] = Relationship(
        back_populates="player"
    )
    pug_participations: list["PugPlayer"] = Relationship(back_populates="player")
    pug_captain_of: list["PugTeam"] = Relationship(back_populates="captain")
    created_pugs: list["Pug"] = Relationship(back_populates="creator")
    tournament_registration_requests: list["TournamentRegistration"] = Relationship(
        back_populates="requester",
        sa_relationship_kwargs={
            "primaryjoin": "Player.id == TournamentRegistration.requested_by"
        },
    )
    tournament_registration_reviews: list["TournamentRegistration"] = Relationship(
        back_populates="reviewer",
        sa_relationship_kwargs={
            "primaryjoin": "Player.id == TournamentRegistration.reviewed_by"
        },
    )
    submitted_results: list["Result"] = Relationship(
        back_populates="submitter",
        sa_relationship_kwargs={"primaryjoin": "Result.submitted_by == Player.id"},
    )
    confirmed_results: list["Result"] = Relationship(
        back_populates="confirmer",
        sa_relationship_kwargs={"primaryjoin": "Result.confirmed_by == Player.id"},
    )
    admin_overridden_results: list["Result"] = Relationship(
        back_populates="admin_overrider",
        sa_relationship_kwargs={"primaryjoin": "Result.admin_override_by == Player.id"},
    )
    bans: list[Ban] = Relationship(
        back_populates="player",
        sa_relationship_kwargs={"primaryjoin": "Ban.player_id == Player.id"},
    )
    issued_bans: list[Ban] = Relationship(
        back_populates="admin",
        sa_relationship=relationship(
            Ban, back_populates="admin", foreign_keys="Ban.issued_by"
        ),
    )
    revoked_bans: list[Ban] = Relationship(
        back_populates="revoking_admin",
        sa_relationship=relationship(
            Ban, back_populates="revoking_admin", foreign_keys="Ban.revoked_by"
        ),
    )

    # New relationships for enhanced features
    availability: list["PlayerAvailability"] = Relationship(back_populates="player")
    submitted_evidence: list["MatchEvidence"] = Relationship(back_populates="submitter")
    evidence_confirmations: list["EvidenceConfirmation"] = Relationship(
        back_populates="confirmer"
    )
    moderation_actions: list[ModerationAction] = Relationship(
        back_populates="player",
        sa_relationship_kwargs={"primaryjoin": "ModerationAction.player_id == Player.id"},
    )
    issued_actions: list[ModerationAction] = Relationship(
        back_populates="admin",
        sa_relationship=relationship(
            ModerationAction, back_populates="admin", foreign_keys="ModerationAction.issued_by"
        ),
    )
