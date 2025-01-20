
from services.auth import auth_service
from admin.service import create_admin_service

admin_service = create_admin_service(auth_service)