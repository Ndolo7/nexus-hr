import calendar
import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ERPClientError(Exception):
    def __init__(self, message: str, status_code: int = None, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class ERPClient:
    """
    Frappe/ERPNext client.
    Uses token auth when ERP_API_SECRET is configured:
      Authorization: token <api_key>:<api_secret>
    """

    def __init__(self):
        self.base_url = settings.ERP_BASE_URL.rstrip("/")
        self.auth_mode = settings.ERP_AUTH_MODE.strip().lower()
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._build_headers(),
            timeout=settings.ERP_TIMEOUT_SECONDS,
            verify=settings.ERP_VERIFY_SSL,
        )

    def _build_authorization_header(self) -> Optional[str]:
        raw_header = settings.ERP_AUTH_HEADER.strip()
        if raw_header:
            return raw_header

        api_key = settings.ERP_API_KEY.strip()
        api_secret = settings.ERP_API_SECRET.strip()
        mode = self.auth_mode or "auto"

        if mode == "none":
            return None
        if mode == "token":
            return f"token {api_key}:{api_secret}" if api_key and api_secret else None
        if mode == "bearer":
            return f"Bearer {api_key}" if api_key else None
        if mode == "raw":
            logger.warning("ERP_AUTH_MODE is 'raw' but ERP_AUTH_HEADER is empty; no Authorization header will be sent.")
            return None
        if mode != "auto":
            logger.warning("Unsupported ERP_AUTH_MODE '%s'. Falling back to auto.", mode)

        if api_key and api_secret:
            return f"token {api_key}:{api_secret}"
        if api_key:
            # Legacy fallback for non-Frappe integrations.
            return f"Bearer {api_key}"
        return None

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        auth_header = self._build_authorization_header()
        if auth_header:
            headers["Authorization"] = auth_header

        site_name = settings.ERP_SITE_NAME.strip()
        if site_name:
            # Required for some Frappe Docker + reverse proxy setups.
            headers["X-Frappe-Site-Name"] = site_name

        return headers

    def _resource_path(self, doctype: str, name: Optional[str] = None) -> str:
        encoded_doctype = quote(doctype, safe="")
        if name:
            return f"/api/resource/{encoded_doctype}/{quote(name, safe='')}"
        return f"/api/resource/{encoded_doctype}"

    @staticmethod
    def _encode_param(value: Any) -> Any:
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return value

    @staticmethod
    def _month_bounds(period: str) -> Sequence[date]:
        try:
            parsed = datetime.strptime(period, "%Y-%m")
        except ValueError as exc:
            raise ERPClientError("Invalid period format. Expected YYYY-MM.") from exc
        first_day = date(parsed.year, parsed.month, 1)
        last_day = date(parsed.year, parsed.month, calendar.monthrange(parsed.year, parsed.month)[1])
        return first_day, last_day

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            encoded_params = {
                key: self._encode_param(value) for key, value in (params or {}).items() if value is not None
            }
            response = await self.client.request(method, endpoint, json=data, params=encoded_params)
            response.raise_for_status()
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError:
                return {"message": response.text}
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            logger.error("ERP request failed (%s %s): %s", method, endpoint, body)
            raise ERPClientError(
                f"ERP HTTP error {exc.response.status_code}",
                status_code=exc.response.status_code,
                response_body=body,
            ) from exc
        except httpx.RequestError as exc:
            logger.error("ERP request transport error to %s: %s", endpoint, exc)
            raise ERPClientError(f"Request Error: {exc}") from exc

    async def list_resource(
        self,
        doctype: str,
        *,
        filters: Optional[List[Any] | Dict[str, Any]] = None,
        fields: Optional[List[str]] = None,
        order_by: str = "modified desc",
        limit_page_length: int = 20,
        limit_start: int = 0,
    ) -> List[Dict[str, Any]]:
        payload = await self._request(
            "GET",
            self._resource_path(doctype),
            params={
                "filters": filters,
                "fields": fields or ["name", "modified"],
                "order_by": order_by,
                "limit_page_length": limit_page_length,
                "limit_start": limit_start,
            },
        )
        return payload.get("data", [])

    async def get_resource(self, doctype: str, name: str, *, fields: Optional[List[str]] = None) -> Dict[str, Any]:
        payload = await self._request(
            "GET",
            self._resource_path(doctype, name),
            params={"fields": fields} if fields else None,
        )
        return payload.get("data", {})

    async def create_resource(self, doctype: str, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = await self._request("POST", self._resource_path(doctype), data=data)
        return payload.get("data", {})

    async def update_resource(self, doctype: str, name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = await self._request("PUT", self._resource_path(doctype, name), data=data)
        return payload.get("data", {})

    async def delete_resource(self, doctype: str, name: str) -> Dict[str, Any]:
        payload = await self._request("DELETE", self._resource_path(doctype, name))
        return payload.get("data", {})

    async def call_method(
        self,
        method_path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        http_method: str = "POST",
    ) -> Dict[str, Any]:
        endpoint = f"/api/method/{method_path}"
        if http_method.upper() == "GET":
            return await self._request("GET", endpoint, params=params)
        return await self._request("POST", endpoint, data=params or {})

    async def ping(self) -> Dict[str, Any]:
        payload = await self.call_method("frappe.auth.get_logged_user", http_method="GET")
        logged_user = payload.get("message") or payload.get("data")
        return {
            "base_url": self.base_url,
            "site_name": settings.ERP_SITE_NAME.strip() or None,
            "auth_mode": self.auth_mode or "auto",
            "logged_user": logged_user,
        }

    async def get_employee_profile(self, employee_id: str) -> Dict[str, Any]:
        """
        Fetch employee profile using Employee document name first,
        then fallback to employee field lookup.
        """
        fields = [
            "name",
            "employee",
            "employee_name",
            "company",
            "designation",
            "department",
            "status",
            "date_of_joining",
            "user_id",
            "cell_number",
            "personal_email",
        ]
        try:
            return await self.get_resource("Employee", employee_id, fields=fields)
        except ERPClientError as exc:
            if exc.status_code != 404:
                raise

        rows = await self.list_resource(
            "Employee",
            filters={"employee": employee_id},
            fields=fields,
            limit_page_length=1,
        )
        if not rows:
            raise ERPClientError(f"Employee '{employee_id}' not found.", status_code=404)
        return rows[0]

    async def get_leave_balance(self, employee_id: str) -> Dict[str, Any]:
        """
        Calculate leave balances from submitted Leave Allocation rows.
        """
        fields = [
            "name",
            "leave_type",
            "from_date",
            "to_date",
            "total_leaves_allocated",
            "unused_leaves",
        ]
        allocations = await self.list_resource(
            "Leave Allocation",
            filters={"employee": employee_id, "docstatus": 1},
            fields=fields,
            limit_page_length=500,
        )

        balances: Dict[str, Dict[str, float]] = {}
        for row in allocations:
            leave_type = row.get("leave_type") or "Unknown"
            allocated = float(row.get("total_leaves_allocated") or 0)
            unused = float(row.get("unused_leaves") or 0)
            current = balances.setdefault(
                leave_type, {"allocated_leaves": 0.0, "unused_leaves": 0.0, "consumed_leaves": 0.0}
            )
            current["allocated_leaves"] += allocated
            current["unused_leaves"] += unused
            current["consumed_leaves"] += max(allocated - unused, 0.0)

        return {
            "employee_id": employee_id,
            "leave_balances": balances,
            "total_unused_leaves": sum(v["unused_leaves"] for v in balances.values()),
        }

    async def create_leave_request(self, employee_id: str, leave_data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "employee": employee_id,
            "leave_type": leave_data.get("leave_type"),
            "from_date": leave_data.get("start_date"),
            "to_date": leave_data.get("end_date"),
            "description": leave_data.get("reason") or "",
        }
        created_doc = await self.create_resource("Leave Application", payload)
        leave_name = created_doc.get("name")
        if not leave_name:
            return created_doc

        try:
            # Submit automatically when allowed by ERP workflow.
            submit_response = await self.call_method(
                "frappe.client.submit",
                {"doctype": "Leave Application", "name": leave_name},
            )
            submitted_doc = submit_response.get("message") or submit_response.get("data")
            if isinstance(submitted_doc, dict):
                return submitted_doc
        except ERPClientError:
            logger.info("Leave Application %s created but not auto-submitted.", leave_name)

        return created_doc

    async def cancel_leave_request(self, employee_id: str, request_id: str) -> Dict[str, Any]:
        leave_doc = await self.get_resource("Leave Application", request_id, fields=["name", "employee", "status", "docstatus"])
        if leave_doc.get("employee") != employee_id:
            raise ERPClientError("Leave request does not belong to the employee.", status_code=403)

        if leave_doc.get("docstatus") == 2:
            return {"name": request_id, "status": "Cancelled", "already_cancelled": True}

        response = await self.call_method(
            "frappe.client.cancel",
            {"doctype": "Leave Application", "name": request_id},
        )
        return response.get("message") or response.get("data") or {"name": request_id, "status": "Cancelled"}

    async def get_payslip_summary(self, employee_id: str, period: str) -> Dict[str, Any]:
        first_day, last_day = self._month_bounds(period)
        fields = [
            "name",
            "employee",
            "employee_name",
            "currency",
            "gross_pay",
            "net_pay",
            "start_date",
            "end_date",
            "posting_date",
            "docstatus",
        ]
        filters = [
            ["employee", "=", employee_id],
            ["start_date", ">=", first_day.isoformat()],
            ["end_date", "<=", last_day.isoformat()],
        ]
        slips = await self.list_resource(
            "Salary Slip",
            filters=filters,
            fields=fields,
            order_by="start_date desc",
            limit_page_length=50,
        )

        return {
            "employee_id": employee_id,
            "period": period,
            "slip_count": len(slips),
            "slips": slips,
            "total_gross_pay": sum(float(s.get("gross_pay") or 0) for s in slips),
            "total_net_pay": sum(float(s.get("net_pay") or 0) for s in slips),
        }

    async def update_employee_contact(self, employee_id: str, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            k: v
            for k, v in contact_data.items()
            if k in {"cell_number", "personal_email", "company_email", "current_address"}
        }
        if not payload:
            raise ERPClientError("No valid Employee contact fields provided.")
        return await self.update_resource("Employee", employee_id, payload)

    async def start_onboarding(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.create_resource("Employee Onboarding", employee_data)

    async def close(self):
        await self.client.aclose()


erp_client = ERPClient()
