
from services.audit import audit_service
from competitions.rounds.service import create_round_service

round_service = create_round_service(audit_service)