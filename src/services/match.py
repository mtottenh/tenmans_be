from matches.service import create_match_service
from services.audit import audit_service
from services.fixture import fixture_service

match_service = create_match_service(audit_service, fixture_service)