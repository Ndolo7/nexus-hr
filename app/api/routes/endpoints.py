from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.schemas.pydantic_models import ChatRequest, ChatResponse, ActionRequest, DocumentUpload
from app.core.agent import agent_core
from app.core.config import settings
from typing import Dict, Any

router = APIRouter()
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.scheme != "Bearer" or credentials.credentials != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Simple mock user resolution for demonstration. In production, validate JWT and extract sub.
    return {"user_id": "admin_emp_123"}

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "service": "Nexus HR Agent"}

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Main endpoint for interacting with the HR Agent via conversational interface.
    """
    try:
        # Pass the query to AgentCore
        result = await agent_core.chat(user_id=request.user_id, query=request.query)
        return ChatResponse(response=result["response"], tools_used=result["tools_used"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/action")
async def execute_action(request: ActionRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Endpoint for executing an explicit ERP action directly (bypassing the conversational loop).
    """
    try:
        result = await agent_core.direct_action(
            user_id=request.user_id,
            action=request.action,
            payload=request.payload
        )
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload_document(request: DocumentUpload, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Upload a new policy/handbook document to the RAG knowledge base.
    """
    # Verify user has HR admin role
    if "admin" not in current_user.get("user_id", "") and "hr" not in current_user.get("user_id", ""):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only HR can upload documents.")
    
    # In a real scenario, trigger a celery task or directly vectorized to pgvector
    return {"status": "success", "message": f"Document '{request.title}' queued for indexing."}
