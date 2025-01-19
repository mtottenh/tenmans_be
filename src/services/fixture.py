from services.audit import audit_service
from services.round import round_service
from competitions.fixtures.service import create_fixture_service

fixture_service = create_fixture_service(audit_service, round_service)