import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.erp_client import ERPClientError, erp_client


class UnauthorizedActionError(Exception):
    pass


class GuardrailsService:
    """
    Permission guardrails backed by ERPNext role data (Has Role).
    """

    HIGH_RISK_ACTIONS = [
        "create_leave_request",
        "update_employee_contact",
        "start_onboarding",
        "create_employee",
        "cancel_leave_request",
        "assign_asset",
    ]

    PRIVILEGED_ROLES = {
        "System Manager",
        "HR Manager",
        "HR User",
    }

    SELF_SERVICE_WRITE_ACTIONS = {
        "create_leave_request",
        "cancel_leave_request",
        "update_employee_contact",
    }

    _ROLE_CACHE_TTL_SECONDS = 300
    _ROLE_CACHE: Dict[str, Tuple[float, List[str], Optional[str]]] = {}

    @classmethod
    async def _resolve_user_roles(cls, user_id: str) -> Tuple[List[str], Optional[str]]:
        now = time.time()
        cached = cls._ROLE_CACHE.get(user_id)
        if cached and now < cached[0]:
            return cached[1], cached[2]

        employee = await erp_client.get_employee_profile(user_id)
        frappe_user = employee.get("user_id")

        roles: List[str] = []
        if frappe_user:
            try:
                role_rows = await erp_client.list_resource(
                    "Has Role",
                    filters={"parent": frappe_user},
                    fields=["role"],
                    limit_page_length=200,
                )
                roles = sorted({row.get("role") for row in role_rows if row.get("role")})
            except ERPClientError:
                roles = []

        cls._ROLE_CACHE[user_id] = (now + cls._ROLE_CACHE_TTL_SECONDS, roles, frappe_user)
        return roles, frappe_user

    @classmethod
    async def get_user_roles(cls, user_id: str) -> List[str]:
        roles, _ = await cls._resolve_user_roles(user_id)
        return roles

    @classmethod
    async def check_permission(cls, user_id: str, action: str, **context: Any) -> bool:
        """
        Enforce access based on ERPNext identity + roles.

        Rules:
        - Read actions (`get_*`) are allowed for own records, or privileged HR/System roles.
        - High-risk actions require privileged roles unless the action is allowed for self-service.
        """
        try:
            roles, _ = await cls._resolve_user_roles(user_id)
        except ERPClientError as exc:
            raise UnauthorizedActionError(f"Unable to resolve user '{user_id}' in ERPNext: {exc}") from exc

        is_privileged = any(role in cls.PRIVILEGED_ROLES for role in roles)
        target_employee_id = context.get("employee_id")
        is_self_access = not target_employee_id or str(target_employee_id) == str(user_id)

        if action.startswith("get_"):
            if is_self_access or is_privileged:
                return True
            raise UnauthorizedActionError(
                f"User {user_id} cannot read data for employee {target_employee_id}."
            )

        if action in cls.HIGH_RISK_ACTIONS:
            if is_privileged:
                return True
            if action in cls.SELF_SERVICE_WRITE_ACTIONS and is_self_access:
                return True
            raise UnauthorizedActionError(
                f"User {user_id} does not have permission to execute '{action}'."
            )

        # Default deny for unknown action groups.
        if is_privileged:
            return True
        raise UnauthorizedActionError(f"Action '{action}' is not permitted for user {user_id}.")

    @classmethod
    def requires_confirmation(cls, action: str) -> bool:
        return action in cls.HIGH_RISK_ACTIONS
