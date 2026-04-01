import httpx
from typing import Any, Dict, Optional
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class ERPClientError(Exception):
    def __init__(self, message: str, status_code: int = None, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

class ERPClient:
    def __init__(self):
        self.base_url = settings.ERP_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.ERP_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        # In a real scenario, use AsyncClient and manage session lifecycle
        self.client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=10.0)

    async def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Base request handler with retries and error handling.
        """
        try:
            response = await self.client.request(method, endpoint, json=data, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred: {e.response.text}")
            raise ERPClientError(f"HTTP error {e.response.status_code}", e.response.status_code, e.response.text)
        except httpx.RequestError as e:
            logger.error(f"An error occurred while requesting {e.request.url!r}.")
            raise ERPClientError(f"Request Error: {str(e)}")

    async def get_employee_profile(self, employee_id: str) -> Dict[str, Any]:
        """Fetch employee profile."""
        return await self._request("GET", f"/employees/{employee_id}")

    async def get_leave_balance(self, employee_id: str) -> Dict[str, Any]:
        """Fetch employee leave balance."""
        return await self._request("GET", f"/employees/{employee_id}/leave-balance")

    async def create_leave_request(self, employee_id: str, leave_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a new leave request."""
        # idempotency key could be passed in headers
        return await self._request("POST", f"/employees/{employee_id}/leave-requests", data=leave_data)

    async def cancel_leave_request(self, employee_id: str, request_id: str) -> Dict[str, Any]:
        """Cancel an existing leave request."""
        return await self._request("DELETE", f"/employees/{employee_id}/leave-requests/{request_id}")

    async def get_payslip_summary(self, employee_id: str, period: str) -> Dict[str, Any]:
        """Fetch payslip summary for a given period."""
        return await self._request("GET", f"/employees/{employee_id}/payslips/{period}")

    async def update_employee_contact(self, employee_id: str, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update employee contact details."""
        return await self._request("PUT", f"/employees/{employee_id}/contact", data=contact_data)

    async def start_onboarding(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        """Start the onboarding process for a new employee."""
        return await self._request("POST", "/onboarding", data=employee_data)

    async def close(self):
        await self.client.aclose()

erp_client = ERPClient()
