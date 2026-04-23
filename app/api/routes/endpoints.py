import hashlib
import hmac
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings
from app.core.agent import agent_core
from app.schemas.pydantic_models import (
    ActionRequest,
    ChatRequest,
    ChatResponse,
    ERPNextPullSyncRequest,
    ERPNextWebhookIngestResponse,
)
from app.services.erp_client import ERPClientError, erp_client
from app.services.erpnext_sync import erpnext_sync_service
from app.services.rag_engine import rag_engine

router = APIRouter()
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_employee_id: str | None = Header(default=None, alias="X-Employee-Id"),
):
    if credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    service_secret = settings.API_SECRET_KEY.strip()

    # Supports either:
    # 1) Authorization: Bearer <API_SECRET_KEY> + X-Employee-Id header
    # 2) Authorization: Bearer <API_SECRET_KEY>:<employee_id>
    if token == service_secret:
        employee_id = (x_employee_id or "").strip()
    elif token.startswith(f"{service_secret}:"):
        employee_id = token.split(":", 1)[1].strip()
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing employee context. Provide X-Employee-Id or append ':<employee_id>' to the bearer token.",
        )

    try:
        employee = await erp_client.get_employee_profile(employee_id)
    except ERPClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee not found in ERPNext.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"ERPNext auth lookup failed: {exc}")

    return {"user_id": employee.get("name") or employee_id, "employee": employee}


def _verify_erpnext_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    secret = settings.ERP_WEBHOOK_SECRET.strip()
    if not secret:
        return True
    if not signature_header:
        return False

    provided = signature_header.strip()
    if "=" in provided:
        provided = provided.split("=", 1)[1].strip()
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "service": "Nexus HR Agent"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Main endpoint for interacting with the HR Agent via conversational interface.
    """
    try:
        allowed_ids = {str(current_user["user_id"])}
        employee_code = current_user.get("employee", {}).get("employee")
        if employee_code:
            allowed_ids.add(str(employee_code))
        if str(request.user_id) not in allowed_ids:
            raise HTTPException(status_code=403, detail="request.user_id must match authenticated employee.")
        result = await agent_core.chat(user_id=current_user["user_id"], query=request.query)
        return ChatResponse(response=result["response"], tools_used=result["tools_used"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/action")
async def execute_action(request: ActionRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Endpoint for executing an explicit ERP action directly (bypassing the conversational loop).
    """
    try:
        allowed_ids = {str(current_user["user_id"])}
        employee_code = current_user.get("employee", {}).get("employee")
        if employee_code:
            allowed_ids.add(str(employee_code))
        if str(request.user_id) not in allowed_ids:
            raise HTTPException(status_code=403, detail="request.user_id must match authenticated employee.")
        result = await agent_core.direct_action(
            user_id=current_user["user_id"],
            action=request.action,
            payload=request.payload
        )
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(..., description="HR handbook or policy file (.pdf, .docx, .txt)"),
    title: str = Form(..., description="Title of the document"),
    category: str = Form("handbook", description="Category: handbook | policy | benefit"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Upload an HR handbook or policy document. Accepts PDF, DOCX, or TXT files.
    The text will be extracted, vectorised, and stored in the RAG knowledge base.
    """
    allowed_types = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    if file.content_type not in allowed_types and not file.filename.endswith((".pdf", ".docx", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a PDF, DOCX, or TXT file.",
        )

    raw_bytes = await file.read()

    try:
        text = rag_engine.extract_text(raw_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not extract text: {e}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="The document appears to be empty.")

    try:
        doc_id = rag_engine.ingest_document(title=title, content=text, category=category)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store document: {e}")

    return {
        "status": "success",
        "message": f"Document '{title}' indexed successfully.",
        "document_id": doc_id,
        "characters_indexed": len(text),
    }


@router.post("/erpnext/sync/pull")
async def pull_erpnext_data(
    request: ERPNextPullSyncRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Pull changed records from ERPNext and store sync checkpoints per DocType.
    """
    try:
        result = await erpnext_sync_service.pull_many(
            doctypes=request.doctypes,
            modified_after=request.modified_after,
            limit_per_doctype=request.limit_per_doctype,
        )
        return {"status": "success", **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/erpnext/sync/checkpoints")
async def list_erpnext_sync_checkpoints(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Inspect stored pull-sync checkpoints per DocType.
    """
    return {"status": "success", "checkpoints": erpnext_sync_service.list_checkpoints()}


@router.post("/erpnext/webhook", response_model=ERPNextWebhookIngestResponse)
async def ingest_erpnext_webhook(
    request: Request,
    x_frappe_webhook_signature: str | None = Header(default=None, alias="X-Frappe-Webhook-Signature"),
    x_erpnext_webhook_signature: str | None = Header(default=None, alias="X-ERPNext-Webhook-Signature"),
):
    """
    Receive ERPNext webhook callbacks and optionally process updated records immediately.
    """
    raw_body = await request.body()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    signature = x_frappe_webhook_signature or x_erpnext_webhook_signature
    signature_valid = _verify_erpnext_webhook_signature(raw_body, signature)
    if settings.ERP_WEBHOOK_SECRET.strip() and not signature_valid:
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    result = await erpnext_sync_service.ingest_webhook(payload, signature_valid=signature_valid)
    return ERPNextWebhookIngestResponse(**result)
