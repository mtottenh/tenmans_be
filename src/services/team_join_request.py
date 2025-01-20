
from teams.join_request.service import create_team_join_request_service
from services.roster import roster_service
from services.team import team_service
from services.audit import audit_service
from services.permission import   permission_service
from services.status import status_transition_service
from services.captain import captain_service
from services.season import season_service

join_request_service = create_team_join_request_service(roster_service, team_service,
                                                        audit_service,
                                                        permission_service,
                                                        status_transition_service,
                                                        captain_service,
                                                        season_service,
                                                        )