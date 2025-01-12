from pydantic import BaseModel
from typing import Optional, Literal


UploadType = Literal["team_logo", "map_image", "player_avatar"]


class UploadRequest(BaseModel):
    """Request for an upload token"""
    filename: str
    content_type: str
    size: int
    upload_type: UploadType
    metadata: Optional[dict] = None

class UploadToken(BaseModel):
    """Response with upload token and metadata"""
    upload_url: str
    token: str
    allowed_types: list[str]
    max_size: int
    expires_in: int  # seconds
