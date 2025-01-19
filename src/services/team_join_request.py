
from teams.join_request.service import create_team_join_request_service
from services.roster import roster_service
from services.team import team_service

join_request_service = create_team_join_request_service(roster_service, team_service)