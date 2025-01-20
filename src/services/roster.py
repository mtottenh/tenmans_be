from services.audit import audit_service
from services.season import season_service
from services.permission import permission_service
from services.status import status_transition_service
from teams.service.roster import create_roster_service


roster_service = create_roster_service(audit_service, season_service, permission_service, status_transition_service)