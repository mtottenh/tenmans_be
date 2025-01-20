from auth.service.role import create_role_service
from services.permission import permission_service

role_service = create_role_service(permission_service)