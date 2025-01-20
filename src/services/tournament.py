from competitions.tournament.service import create_tournament_service
from services.team import team_service
from services.match import match_service
from services.audit import audit_service

tournament_service = create_tournament_service(team_service, match_service, audit_service)