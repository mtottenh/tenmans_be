

from services.audit import audit_service
from services.roster import roster_service
from services.permission import permission_service
from services.status import status_transition_service
from teams.service.team import create_team_service
from services.captain import captain_service
from services.season import season_service

team_service = create_team_service(audit_service, 
                                   roster_service,
                                   season_service,
                                   captain_service,
                                   permission_service, 
                                   status_transition_service)