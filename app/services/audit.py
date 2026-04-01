from sqlalchemy.orm import Session
from app.models.db_models import AuditLog
from typing import Dict, Any, List, Optional
import json

class AuditService:
    @staticmethod
    def log_action(
        db: Session,
        user_id: str,
        request_intent: str,
        tools_called: List[str],
        payload_used: Dict[str, Any],
        result_returned: Dict[str, Any],
        approval_trail: Optional[Dict[str, Any]] = None,
        status: str = "completed"
    ) -> AuditLog:
        """
        Record a detailed trail of agent actions.
        """
        audit_entry = AuditLog(
            user_id=user_id,
            request_intent=request_intent,
            tools_called=tools_called,
            payload_used=payload_used,
            result_returned=result_returned,
            approval_trail=approval_trail,
            status=status
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        return audit_entry
