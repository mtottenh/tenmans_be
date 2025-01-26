from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, EmailStr, Field, UUID4, field_validator, model_validator
from typing import Dict, Optional, List, Self, Set
from datetime import datetime
from enum import StrEnum

from teams.base_schemas import TeamBasic


class AuthType(StrEnum):
    STEAM = "steam"
    EMAIL = "email"

class PlayerStatus(StrEnum):
    """Unified player status including verification states"""
    # Active states
    ACTIVE = "active"              # Verified and active
    PENDING_VERIFICATION = "pending_verification"  # New account awaiting verification
    VERIFICATION_REJECTED = "verification_rejected"  # Failed verification
    
    # Inactive states
    INACTIVE = "inactive"          # Self-deactivated
    SUSPENDED = "suspended"        # Temporary admin suspension
    BANNED = "banned"             # Permanent ban
    DELETED = "deleted"           # Soft deleted


class ScopeType(StrEnum):
    GLOBAL = "global"
    TEAM = "team"
    TOURNAMENT = "tournament"

# Request Schemas
class PlayerEmailCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    steam_id: str
    submitted_evidence: Optional[str]  # For verification process

    @field_validator('steam_id')
    def validate_steam_id(cls, v):
        if not v.isdigit():
            raise ValueError('Steam ID must be numeric')
        return v

class PlayerSteamCreate(BaseModel):
    steam_id: str
    name: Optional[str] = None  # Can be pulled from Steam profile if not provided

    @field_validator('steam_id')
    def validate_steam_id(cls, v):
        if not v.isdigit():
            raise ValueError('Steam ID must be numeric')
        return v

class PlayerLogin(BaseModel):
    email: EmailStr
    password: str

class SteamLoginCallback(BaseModel):
    steam_id: str
    steam_token: str

class PlayerVerificationUpdate(BaseModel):
    status: PlayerStatus
    admin_notes: Optional[str]
    verification_date: datetime = Field(default_factory=datetime.now)


class PlayerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = Field(None)
    password: Optional[str] = Field(None, min_length=8)
    steam_id: Optional[str]

    

class PermissionCreate(BaseModel):
    name: str
    description: str

class RoleCreate(BaseModel):
    name: str
    permissions: List[UUID4]

class PlayerRoleAssign(BaseModel):
    role_id: UUID4
    scope_type: str = Field(..., pattern="^(global|team|tournament)$")
    scope_id: Optional[UUID4] = None

    @model_validator(mode='after')
    def validate_scope_id(self) -> Self:
        if self.scope_type != 'global' and self.scope_id is None:
            raise ValueError('scope_id is required for non-global scopes')
        return self

# Response Schemas
class Permission(BaseModel):
    id: UUID4
    name: str
    description: str

    model_config = ConfigDict(from_attributes=True)

class Role(BaseModel):
    id: UUID4
    name: str
    permissions: List[Permission]

    model_config = ConfigDict(from_attributes=True)

class PlayerRole(BaseModel):
    role: Role
    scope_type: str
    scope_id: Optional[UUID4]

    model_config = ConfigDict(from_attributes=True)

class PlayerBase(BaseModel):
    id: UUID4
    name: str
    email: Optional[EmailStr]
    steam_id: str
    auth_type: AuthType
    status: PlayerStatus
    current_elo: Optional[int]
    highest_elo: Optional[int]
    created_at: datetime
    updated_at: datetime
    roles: List[Role]
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


class VerificationRequestCreate(BaseModel):
    submitted_evidence: Optional[str]
    notes: Optional[str]

class VerificationRequestResponse(BaseModel):
    id: UUID4
    player_id: UUID4
    status: PlayerStatus
    submitted_evidence: Optional[str]
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
    
class PlayerPrivate(PlayerBase):
    verification_notes: Optional[str]

class PlayerPublic(PlayerBase):
    pass

class PlayerWithTeamBasic(PlayerPublic):
    team: Optional[TeamBasic]
    is_captain: bool

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    auth_type: AuthType

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class PlayerUpdate(BaseModel):
    name: str


class PermissionTemplate:
    """Predefined permission templates for common scenarios"""
    
    TEMPLATES = {
        "user": {
            "roles": ["user"],
            "permissions": [
                "view_tournaments",
                "join_tournaments",
                "view_teams",
                "join_teams",
                "submit_results",
                "view_matches"
            ],
            "scope_type": ScopeType.GLOBAL
        },
        "team_captain": {
            "roles": ["team_captain"],
            "permissions": [
                "manage_team",
                "manage_roster",
                "submit_results",
                "schedule_matches",
                "confirm_results"
            ],
            "scope_type": ScopeType.TEAM
        },
        "tournament_admin": {
            "roles": ["tournament_admin"],
            "permissions": [
                "manage_tournament",
                "manage_fixtures",
                "manage_results",
                "manage_participants",
                "verify_results"
            ],
            "scope_type": ScopeType.TOURNAMENT
        },
        "moderator": {
            "roles": ["moderator"],
            "permissions": [
                "moderate_chat",
                "manage_bans",
                "verify_users",
                "manage_reports"
            ],
            "scope_type": ScopeType.GLOBAL
        },
        "league_admin": {
            "roles": ["league_admin"],
            "permissions": [
                "manage_seasons",
                "manage_tournaments",
                "manage_teams",
                "manage_users",
                "manage_roles",
                "manage_permissions",
                "manage_maps"
            ],
            "scope_type": ScopeType.GLOBAL
        }
    }

    # Default permissions that every authenticated user should have
    DEFAULT_USER_PERMISSIONS = [
        "view_tournaments",
        "join_tournaments",
        "view_teams",
        "join_teams",
        "submit_results",
        "view_matches"
    ]

    @classmethod
    def get_template(cls, template_name: str) -> dict:
        """Get a permission template by name"""
        if template_name not in cls.TEMPLATES:
            raise ValueError(f"Template {template_name} not found")
        return cls.TEMPLATES[template_name]

    @classmethod
    def list_templates(cls) -> List[str]:
        """Get list of available templates"""
        return list(cls.TEMPLATES.keys())

    @classmethod
    def get_default_permissions(cls) -> List[str]:
        """Get list of default user permissions"""
        return cls.DEFAULT_USER_PERMISSIONS.copy()


@dataclass
class PermissionAuditResult:
    """Container for permission audit results"""
    player_id: str
    player_name: str
    steam_id: str
    roles: List[str]
    global_permissions: Set[str]
    team_permissions: Dict[str, Set[str]]  # team_id -> permissions
    tournament_permissions: Dict[str, Set[str]]  # tournament_id -> permissions
    issues: List[str]