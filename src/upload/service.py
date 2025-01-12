from fastapi import APIRouter, Depends, UploadFile, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from typing import Optional, Literal
from pathlib import Path
import aiofiles
import os
import shutil
from werkzeug.utils import secure_filename
from datetime import timedelta

from src.db.main import get_session
from src.auth.dependencies import get_current_player
from src.auth.models import Player
from src.state.service import StateService, StateType, get_state_service
from .models import UploadRequest, UploadToken, UploadType
class UploadConfig:
    """Configuration for different upload types"""
    CONFIGS = {
        "team_logo": {
            "allowed_types": ["image/jpeg", "image/png"],
            "max_size": 5_000_000,  # 5MB
            "base_path": "logo_store",
            "expiry": timedelta(minutes=30)
        },
        "map_image": {
            "allowed_types": ["image/jpeg", "image/png"],
            "max_size": 10_000_000,  # 10MB
            "base_path": "map_store",
            "expiry": timedelta(minutes=30)
        },
        "player_avatar": {
            "allowed_types": ["image/jpeg", "image/png"],
            "max_size": 2_000_000,  # 2MB
            "base_path": "avatar_store",
            "expiry": timedelta(minutes=30)
        }
    }

class UploadService:
    def __init__(self, state_service: StateService):
        self.state_service = state_service
    
    def validate_upload_request(self, request: UploadRequest) -> None:
        """Validate upload request against config"""
        config = UploadConfig.CONFIGS.get(request.upload_type)
        if not config:
            raise ValueError(f"Invalid upload type: {request.upload_type}")
            
        if request.content_type not in config["allowed_types"]:
            raise ValueError(f"Invalid content type for {request.upload_type}")
            
        if request.size > config["max_size"]:
            raise ValueError(f"File too large for {request.upload_type}")
    
    async def create_upload_token(
        self,
        request: UploadRequest,
        player: Player
    ) -> UploadToken:
        """Create an upload token for a file"""
        self.validate_upload_request(request)
        
        config = UploadConfig.CONFIGS[request.upload_type]
        
        # Store upload request in state service
        state_id = await self.state_service.store_state(
            StateType.FILE_UPLOAD,
            request,
            metadata={
                "player_id": str(player.uid),
                "original_filename": request.filename
            },
            custom_expiry=config["expiry"]
        )
        
        return UploadToken(
            upload_url=f"/api/v1/uploads/{state_id}",
            token=state_id,
            allowed_types=config["allowed_types"],
            max_size=config["max_size"],
            expires_in=int(config["expiry"].total_seconds())
        )
    
    async def process_upload(
        self,
        token: str,
        file: UploadFile,
        final_id: Optional[str] = None
    ) -> str:
        """Process an upload and return the file path"""
        result = await self.state_service.retrieve_state(
            StateType.FILE_UPLOAD,
            token,
            UploadRequest
        )
        
        if not result:
            raise ValueError("Invalid or expired upload token")
            
        request, metadata = result
        
        # Validate upload matches request
        if file.content_type != request.content_type:
            raise ValueError("File type doesn't match request")
            
        config = UploadConfig.CONFIGS[request.upload_type]
        
        # Determine paths
        temp_dir = Path(os.getcwd()) / config["base_path"] / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        filename = secure_filename(metadata["original_filename"])
        temp_path = temp_dir / filename
        
        # Save file to temp location
        async with aiofiles.open(temp_path, 'wb') as out_file:
            while content := await file.read(1024):
                await out_file.write(content)
        
        # If final_id provided, move to final location
        if final_id:
            final_dir = Path(os.getcwd()) / config["base_path"] / final_id
            final_dir.mkdir(parents=True, exist_ok=True)
            final_path = final_dir / filename
            shutil.move(temp_path, final_path)
            return str(final_path)
            
        return str(temp_path)
