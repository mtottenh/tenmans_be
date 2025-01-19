from auth.service.auth import create_auth_service
from services.identity import identity_service
from services.audit import audit_service

auth_service = create_auth_service(identity_service, audit_service)