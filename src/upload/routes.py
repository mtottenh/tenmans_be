from fastapi import APIRouter, Depends, UploadFile, HTTPException
from config import Config
from typing import Optional
from upload.models import UploadRequest, UploadToken
from auth.dependencies import get_current_player
from auth.models import Player
from services.upload import upload_service

upload_router = APIRouter(prefix="/uploads")

@upload_router.post("/request", response_model=UploadToken)
async def request_upload(
    request: UploadRequest,
    current_player: Player = Depends(get_current_player)
):
    """Request an upload token"""
    try:
        return await upload_service.create_upload_token(request, current_player)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@upload_router.post("/{token}")
async def process_upload(
    token: str,
    file: UploadFile,
    final_id: Optional[str] = None
):
    """Handle file upload with token"""
    try:
        filepath = await upload_service.process_upload(token, file, final_id)
        return {"filepath": filepath}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
