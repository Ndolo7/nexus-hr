# Nexus HR AI Service

Nexus HR is an independent AI orchestration layer sitting above business APIs. This service is designed to handle multi-step HR workflows, retrieve HR policies securely using a RAG engine, and act safely on ERP services via a managed Tool Registry.

## Architecture

1. **FastAPI Gateway**: The main entry point for chat interfaces and direct API actions.
2. **Agent Core**: LLM-powered orchestration that determines user intent and selects either Tool execution or RAG retrieval.
3. **RAG Engine**: Powered by `pgvector`, it retrieves verified HR policy documents.
4. **Tool Registry**: Safe, wrapped functions matching ERP actions (e.g., `create_leave_request`, `get_payslip`).
5. **Guardrails & Audit Logging**: RBAC permission checks, high-risk action confirmation limits, and detailed tool execution auditing.
6. **ERP Integration Client**: An robust HTTP client using `httpx` for standardizing requests to the ERP backend.

## Tech Stack
- FastAPI
- PostgreSQL + pgvector (via SQLAlchemy & Alembic)
- Pydantic
- Httpx
- OpenAI SDK (for LLM tool calling loop)
- FastAPI Security (`HTTPBearer` for authentication)

## Directory Structure
- `app/api/`: FastAPI routing and endpoints (`/chat`, `/action`, `/upload`, `/health`).
- `app/core/`: Configuration (env driven), Security, Guardrails, and OpenAI Agent loop.
- `app/models/`: SQLAlchemy and pgvector DB schemas (AuditLog, HRDocument).
- `app/schemas/`: Pydantic input/output schemas.
- `app/services/`: HTTP ERP client, Audit Logging, and RAG Engine logics.
- `app/tools/`: The Tool Registry and concrete implementations of tools exposed to the Agent.
- `app/worker/`: Background workers (Celery) placeholder for document vectorization.

## Setup Instructions

1. **Create Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**:
   Copy the provided `.env.example` file to `.env` and fill in your real secrets (`DATABASE_URL`, `OPENAI_API_KEY`, `API_SECRET_KEY`, etc.):
   ```bash
   cp .env.example .env
   ```

4. **Initialize Database** (Ensure PostgreSQL with pgvector is running):
   ```bash
   alembic upgrade head
   ```

5. **Run the Application**:
   ```bash
   uvicorn app.main:app --reload
   ```