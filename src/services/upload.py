

from upload.service import UploadService
from services.state import state_service

upload_service = UploadService(state_service)