

from auth.service.status import create_player_status_service
from services.identity import identity_service
from services.audit import audit_service
from services.permission import permission_service
from services.status import status_transition_service

player_status_service = create_player_status_service(identity_service, audit_service, permission_service, status_transition_service)