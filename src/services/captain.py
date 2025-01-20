
from teams.service.captain import create_captain_service
from services.audit import audit_service
from services.permission import permission_service
from services.status import status_transition_service

captain_service = create_captain_service(audit_service, permission_service, status_transition_service)