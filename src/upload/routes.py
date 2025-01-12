from fastapi import APIRouter, Depends, UploadFile, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from typing import Optional, Literal
from pathlib import Path
import aiofiles
import os
import shutil
from upload.models import UploadRequest, UploadToken
from upload.service import UploadService
from werkzeug.utils import secure_filename
from datetime import timedelta

from db.main import get_session
from auth.dependencies import get_current_player
from auth.models import Player
from state.service import StateService, StateType, get_state_service


upload_router = APIRouter(prefix="/uploads")

@upload_router.post("/request", response_model=UploadToken)
async def request_upload(
    request: UploadRequest,
    upload_service: UploadService = Depends(lambda: UploadService(get_state_service())),
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
    final_id: Optional[str] = None,
    upload_service: UploadService = Depends(lambda: UploadService(get_state_service()))
):
    """Handle file upload with token"""
    try:
        filepath = await upload_service.process_upload(token, file, final_id)
        return {"filepath": filepath}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
