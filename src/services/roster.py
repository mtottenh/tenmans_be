from services.audit import audit_service
from teams.service.roster import create_roster_service


roster_service = create_roster_service(audit_service)