from pydantic import BaseModel, ConfigDict, EmailStr, Field, UUID4, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from enum import StrEnum

from teams.base_schemas import TeamBasic


class AuthType(StrEnum):
    STEAM = "steam"
    EMAIL = "email"

class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

class PlayerRole(StrEnum):
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"

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
    status: VerificationStatus
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
    def validate_scope_id(self):
        if self.scope_type != 'global' and self.scope_id is None:
            raise ValueError('scope_id is required for non-global scopes')
        return v

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
    uid: UUID4
    name: str
    email: Optional[EmailStr]
    steam_id: str
    auth_type: AuthType
    verification_status: VerificationStatus
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
    player_uid: UUID4
    status: VerificationStatus
    submitted_evidence: Optional[str]
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
    
class PlayerPrivate(PlayerBase):
    verification_notes: Optional[str]
    roles: List[PlayerRole]

class PlayerPublic(PlayerBase):
    pass

class PlayerWithTeamBasic(PlayerPublic):
    team: Optional[TeamBasic]

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    auth_type: AuthType

class RefreshTokenRequest(BaseModel):
    refresh_token: str
