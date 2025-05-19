from services.audit import audit_service
from services.permission import permission_service
from status.service import create_enhanced_status_transition_service


status_transition_service = create_enhanced_status_transition_service(
    audit_service, permission_service
)
