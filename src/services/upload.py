from services.state import state_service
from upload.service import UploadService


upload_service = UploadService(state_service)
