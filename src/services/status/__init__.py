

from status.service import create_status_transition_service
from services.audit import audit_service
from services.permission import permission_service


status_transition_service = create_status_transition_service(audit_service, permission_service)