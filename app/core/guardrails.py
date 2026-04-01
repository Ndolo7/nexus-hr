from typing import Dict, Any, List

class UnauthorizedActionError(Exception):
    pass

class GuardrailsService:
    
    # Mock roles mapping for demonstration
    USER_ROLES = {
        "admin_user": ["read", "write", "approve"],
        "hr_user": ["read", "write"],
        "employee_user": ["read"]
    }

    # High-risk operations that require specific confirmation or roles
    HIGH_RISK_ACTIONS = [
        "create_leave_request",
        "update_employee_contact",
        "start_onboarding",
        "create_employee",
        "cancel_leave_request",
        "assign_asset"
    ]

    @classmethod
    def check_permission(cls, user_id: str, action: str):
        """
        Check if a user has basic permission for an action.
        This is a simple RBAC implementation. Let's assume user_id suffix defines role for simplicity.
        """
        role = "employee_user"
        if "admin" in user_id:
            role = "admin_user"
        elif "hr" in user_id:
            role = "hr_user"

        permissions = cls.USER_ROLES.get(role, [])
        
        # Read operations usually start with 'get'
        if action.startswith("get_"):
            if "read" not in permissions:
                raise UnauthorizedActionError(f"User {user_id} does not have access for read action {action}.")
        elif action in cls.HIGH_RISK_ACTIONS:
            if "write" not in permissions:
                raise UnauthorizedActionError(f"User {user_id} does not have access for write action {action}.")
        
        return True

    @classmethod
    def requires_confirmation(cls, action: str) -> bool:
        """
        Check if the action requires explicit user confirmation
        """
        return action in cls.HIGH_RISK_ACTIONS
