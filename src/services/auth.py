from auth.service.auth import create_auth_service
from services.identity import identity_service
from services.audit import audit_service
from services.token import token_service
from services.role import role_service
from services.permission import permission_service
from services.status import status_transition_service
from services.status.player import player_status_service

auth_service = create_auth_service(identity_service,
                                   token_service, 
                                   audit_service, 
                                   permission_service, 
                                   role_service, 
                                   status_transition_service, 
                                   player_status_service)