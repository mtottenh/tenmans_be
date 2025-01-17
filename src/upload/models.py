from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Literal
from enum import StrEnum


class UploadType(StrEnum):
    TEAM_LOGO = "team_logo"
    PLAYER_AVATAR = "player_avatar"
    MAP_IMAGE = "map_image"
    TOURNAMENT_BANNER = "tournament_banner"



class UploadRequest(BaseModel):
    """Request for an upload token"""
    filename: str
    content_type: str
    size: int
    upload_type: UploadType
    metadata: Optional[dict] = None

class UploadTokenData(BaseModel):
    allowed_extensions: list[str]
    max_size: int
    expires_in: int  # seconds


class UploadToken(UploadTokenData):
    """Response with upload token and metadata"""
    upload_url: str
    token: str


class UploadResult(BaseModel):
    file_path: str
    original_filename: str
    upload_type: UploadType
    is_temp: bool
    file_size: int
    uploaded_at: datetime
