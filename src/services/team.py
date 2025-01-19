

from services.audit import audit_service
from services.roster import roster_service
from teams.service.team import create_team_service
from services.season import season_service
team_service = create_team_service(audit_service, roster_service, season_service)