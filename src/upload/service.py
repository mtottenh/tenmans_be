from fastapi import APIRouter, Depends, UploadFile, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from typing import Dict, Optional, Literal, Tuple
from pathlib import Path, PurePath
import aiofiles
import os
import shutil
from werkzeug.utils import secure_filename
from werkzeug.security import safe_join
from datetime import datetime, timedelta

from db.main import get_session
from auth.dependencies import get_current_player
from auth.models import Player
from state.service import StateService, StateType, get_state_service
from .models import UploadRequest, UploadResult, UploadToken, UploadType
class UploadConfig:
    """Configuration for different upload types"""
    CONFIGS = {
        UploadType.TEAM_LOGO : {
            "allowed_extensions": ["image/jpeg", "image/png"],
            "max_size": 5_000_000,  # 5MB
            "storage_path": "/app/logo_store",

        },
        UploadType.MAP_IMAGE: {
            "allowed_extensions": ["image/jpeg", "image/png"],
            "max_size": 10_000_000,  # 10MB
            "storage_path": "/app/map_store",

        },
         UploadType.PLAYER_AVATAR: {
            "allowed_extensions": ["image/jpeg", "image/png"],
            "max_size": 2_000_000,  # 2MB
            "storage_path": "/app/avatar_store",

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
            
        if request.content_type not in config["allowed_extensions"]:
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
            state_type=StateType.FILE_UPLOAD,
            data=request,
            metadata={
                "player_id": str(player.id),
                "original_filename": request.filename,
                "created_at" : str(datetime.utcnow()),
            },
        )
        expiry_time = self.state_service.get_expr_time(StateType.FILE_UPLOAD)
        return UploadToken(
            upload_url=f"/api/v1/uploads/{state_id}",
            token=state_id,
            allowed_extensions=config["allowed_extensions"],
            max_size=config["max_size"],
            expires_in=int(expiry_time.total_seconds())
        )
    
    async def validate_upload_token(self, token: str, file_content_type: Optional[str], final_id: Optional[str]) -> Tuple[UploadRequest, Dict]:
        """Process an upload and return the file path"""

        # Lets check we don't have a directory for the final ID!
        if final_id:
            path = PurePath(final_id)
            if len(path.parents()) > 0:
                raise ValueError("Final ID cannot be a directory")

        result = await self.state_service.retrieve_state(
            StateType.FILE_UPLOAD,
            token,
            UploadRequest,
            delete = True
        )
        
        if not result:
            raise ValueError("Invalid or expired upload token")
            
        request, metadata = result
        
        # Validate upload matches request
        if file_content_type != request.content_type:
            raise ValueError("File type doesn't match request")

        # if request.used:
        #     raise ValueError("Upload token has already been used")
        
        #TODO Validate upload_type if request.upload_type != 
        
        return (request, metadata)


    async def process_upload(
        self,
        token: str,
        file: UploadFile,
        final_id: Optional[str] = None
    ) -> str:
        """Process an upload and return the file path"""
        (request, metadata) = await self.validate_upload_token(token, file.content_type, final_id)

        # TODO validate file size
        file_path = await self.store_file(file, metadata, request.upload_type, final_id)

        await self.state_service.store_state(
            state_type=StateType.FILE_UPLOAD_RESULT,
            data=UploadResult(
                file_path=file_path,
                is_temp=final_id is None,
                upload_type=request.upload_type,
                original_filename=request.filename,
                file_size=request.size,
                uploaded_at=datetime.utcnow()
            ),
            state_id=token,
        )

        return file_path

    async def store_file(self, file: UploadFile, metadata: Dict, upload_type: UploadType, final_id: Optional[str]):

        final_dir = None
        if final_id:
            final_dir = secure_filename(final_id)
            final_dir = PurePath(final_dir)
            final_dir = final_dir.stem
            final_dir = Path(safe_join(os.getcwd(),config["storage_path"], final_dir))

        # Determine paths
        config = UploadConfig.CONFIGS[upload_type]
        temp_dir = Path(os.getcwd()) / config["storage_path"] / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        filename = secure_filename(metadata["original_filename"])
        temp_path = temp_dir / filename
        
        # Save file to temp location
        async with aiofiles.open(temp_path, 'wb') as out_file:
            while content := await file.read(1024):
                await out_file.write(content)
        
        # If final_id provided, move to final location

        if final_dir:
            final_dir.mkdir(parents=True, exist_ok=True)
            final_path = final_dir / filename
            shutil.move(temp_path, final_path)
            return str(final_path)
            
        return str(temp_path)
    
    async def move_upload_if_temp(self, upload_result: UploadResult, dir_name: str) -> str:
        """Move a temporary upload to a directory called 'name'"""
        if not upload_result.is_temp:
            return upload_result.file_path
        config = UploadConfig.CONFIGS[upload_result.upload_type]

        final_dir = secure_filename(dir_name)
        final_dir = PurePath(final_dir)
        final_dir = final_dir.stem
        final_dir = Path(safe_join(config["storage_path"], final_dir))
        if final_dir is None:
            raise ValueError(f"Invalid final directory name supplied {dir_name}")
        final_dir.mkdir(parents=True, exist_ok=True)
        file_extension = "".join(PurePath(upload_result.file_path).suffixes)
        temp_filename = Path('logo' + file_extension)

        final_path = final_dir / temp_filename
        shutil.move(upload_result.file_path, final_path)
        return str(final_path)

    async def delete_file(self, filepath: str) -> bool:
        """
        Deletes a stored file.
        Useful for cleanup if resource creation fails.
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        except Exception:
            return False


    async def get_upload_result(self, token_id: str) -> Optional[UploadResult]:
        """
        Retrieves the result of a completed upload from the state service.
        Returns None if token is invalid or upload hasn't completed.
        """
        result = await self.state_service.retrieve_state(
            state_type=StateType.FILE_UPLOAD_RESULT,
            state_id=token_id,
            model_class=UploadResult,
            delete=False  # Keep the result for audit purposes
        )
        
        if not result:
            return None
            
        upload_result, _ = result
        return upload_result