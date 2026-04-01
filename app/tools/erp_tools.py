from app.tools.registry import registry
from app.services.erp_client import erp_client
from app.core.guardrails import GuardrailsService
from typing import Dict, Any

@registry.register(
    name="get_employee_profile",
    description="Fetch the profile details of an employee.",
    schema={
        "type": "object",
        "properties": {
            "employee_id": {"type": "string", "description": "The unique ID of the employee"}
        },
        "required": ["employee_id"]
    }
)
async def tool_get_employee_profile(employee_id: str, user_id: str) -> Dict[str, Any]:
    GuardrailsService.check_permission(user_id, "get_employee_profile")
    return await erp_client.get_employee_profile(employee_id)

@registry.register(
    name="get_leave_balance",
    description="Get the leave balance for an employee.",
    schema={
        "type": "object",
        "properties": {
            "employee_id": {"type": "string", "description": "The unique ID of the employee"}
        },
        "required": ["employee_id"]
    }
)
async def tool_get_leave_balance(employee_id: str, user_id: str) -> Dict[str, Any]:
    GuardrailsService.check_permission(user_id, "get_leave_balance")
    return await erp_client.get_leave_balance(employee_id)

@registry.register(
    name="create_leave_request",
    description="Submit a new leave request for an employee.",
    schema={
        "type": "object",
        "properties": {
            "employee_id": {"type": "string", "description": "The unique ID of the employee"},
            "leave_type": {"type": "string", "description": "Type of leave (e.g., Annual, Sick)"},
            "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
            "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
            "reason": {"type": "string", "description": "Reason for the leave"}
        },
        "required": ["employee_id", "leave_type", "start_date", "end_date"]
    }
)
async def tool_create_leave_request(employee_id: str, leave_type: str, start_date: str, end_date: str, user_id: str, reason: str = "") -> Dict[str, Any]:
    GuardrailsService.check_permission(user_id, "create_leave_request")
    leave_data = {
        "leave_type": leave_type,
        "start_date": start_date,
        "end_date": end_date,
        "reason": reason
    }
    return await erp_client.create_leave_request(employee_id, leave_data)

@registry.register(
    name="get_payslip_summary",
    description="Get a summary of an employee's payslip for a specific period.",
    schema={
        "type": "object",
        "properties": {
            "employee_id": {"type": "string", "description": "The unique ID of the employee"},
            "period": {"type": "string", "description": "The period for the payslip, e.g., '2023-10'"}
        },
        "required": ["employee_id", "period"]
    }
)
async def tool_get_payslip_summary(employee_id: str, period: str, user_id: str) -> Dict[str, Any]:
    GuardrailsService.check_permission(user_id, "get_payslip_summary")
    return await erp_client.get_payslip_summary(employee_id, period)
