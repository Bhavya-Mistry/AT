# backend/audit_service.py
from sqlalchemy.orm import Session
import models


def log_action(
    db: Session,
    actor_id: int,
    patient_id: int,
    action: str,
    resource_type: str = None,
    resource_id: str = None,
):
    """Saves a HIPAA-compliant audit log to the database."""
    audit_entry = models.AuditLog(
        actor_id=actor_id,
        patient_id=patient_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry
