# Nexus HR AI Service

Nexus HR is an independent AI orchestration layer sitting above business APIs. This service handles multi-step HR workflows, retrieves HR policies securely using a RAG engine, and acts safely on ERP services via a managed Tool Registry.

---

## Architecture

1. **FastAPI Gateway** — Entry point for chat interfaces and direct API actions.
2. **Agent Core** — LLM-powered orchestration (Google Gemini) that resolves user intent and dispatches Tool execution or RAG retrieval.
3. **RAG Engine** — Powered by `pgvector` + Google Embeddings; retrieves verified HR policy documents and handbooks.
4. **Tool Registry** — Safe, wrapped functions matching ERP actions (e.g., `create_leave_request`, `get_payslip`).
5. **Guardrails & Audit Logging** — RBAC permission checks, high-risk action confirmation limits, and detailed tool execution auditing.
6. **ERP Integration Client** — Frappe/ERPNext HTTP client (`httpx`) using API key/secret token auth.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| LLM | Google Gemini 1.5 Flash (`langchain-google-genai`) |
| Embeddings | Google Generative AI Embeddings |
| Vector DB | PostgreSQL + pgvector (via SQLAlchemy & Alembic) |
| Validation | Pydantic v2 |
| HTTP Client | HTTPX |
| Auth | FastAPI `HTTPBearer` |
| Background Jobs | Celery (Redis broker) |

---

## Directory Structure

```
app/
├── api/routes/endpoints.py   # /chat, /action, /upload, /health
├── core/                     # Config, security, guardrails, agent loop
├── models/                   # SQLAlchemy + pgvector schemas (AuditLog, HRDocument)
├── schemas/                  # Pydantic I/O models
├── services/                 # ERPNext client, sync service, audit logger, RAG engine
├── tools/                    # Tool Registry + concrete ERP tool implementations
└── worker/                   # Celery background worker (document vectorisation)
```

---

## Setup Instructions

### 1. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy the example env file and fill in your secrets:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL="postgresql://user:password@localhost:5432/nexus_hr"
REDIS_URL="redis://localhost:6379/0"
API_SECRET_KEY="your-secret-key"

# ERPNext / Frappe
ERP_BASE_URL="https://erp.example.com"
ERP_API_KEY="your-frappe-api-key"
ERP_API_SECRET="your-frappe-api-secret"
ERP_VERIFY_SSL=true
ERP_TIMEOUT_SECONDS=15
ERP_WEBHOOK_SECRET="optional-webhook-hmac-secret"

# Google AI Studio — get free key at https://aistudio.google.com/app/apikey
GOOGLE_API_KEY="AIza..."
```

### 4. Initialize Database

Ensure PostgreSQL with the `pgvector` extension is running, then apply migrations:

```bash
alembic upgrade head
```

### 5. Run the Application

```bash
uvicorn app.main:app --reload
```

The API will be live at `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.

---

## Uploading the HR Handbook

The `/upload` endpoint indexes policy documents into the RAG knowledge base so the agent can answer HR policy questions against your real company content.

### Authentication

All endpoints require a Bearer token. Use your `API_SECRET_KEY` from `.env`:

```
Authorization: Bearer <API_SECRET_KEY>
X-Employee-Id: <ERPNext Employee ID>
```

You can alternatively include employee context in the bearer token itself:

```
Authorization: Bearer <API_SECRET_KEY>:<ERPNext Employee ID>
```

### Upload via cURL

```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -H "Authorization: Bearer <your-api-secret-key>" \
  -F "file=@/path/to/employee-handbook.pdf" \
  -F "title=Employee Handbook 2025" \
  -F "category=handbook"
```

### Upload via the Swagger UI

1. Open `http://localhost:8000/docs`
2. Click **Authorize** (top right) → enter your `API_SECRET_KEY`
3. Expand **POST /api/v1/upload**
4. Click **Try it out** and fill in:
   - `file` — upload `.pdf`, `.docx`, or `.txt`
   - `title` — e.g. `"Annual Leave Policy"`
   - `category` — `"handbook"` | `"policy"` | `"benefit"`
5. Click **Execute**

### Accepted Categories

| Category | Description |
|---|---|
| `handbook` | Full employee handbook |
| `policy` | Standalone HR policies (leave, code of conduct, etc.) |
| `benefit` | Benefits and compensation documents |

> **Note:** Each uploaded document is chunked and vectorised into pgvector. The RAG engine will then automatically retrieve relevant chunks when employees ask policy questions via `/chat`.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Service health check |
| `POST` | `/api/v1/chat` | Conversational HR agent |
| `POST` | `/api/v1/action` | Direct ERP action (bypass chat) |
| `POST` | `/api/v1/upload` | Upload HR handbook / policy document |
| `POST` | `/api/v1/erpnext/sync/pull` | Pull-sync ERPNext DocTypes (`Employee`, `Attendance`, `Leave Application`, `Salary Slip`) |
| `GET` | `/api/v1/erpnext/sync/checkpoints` | View last sync checkpoint per DocType |
| `POST` | `/api/v1/erpnext/webhook` | Receive ERPNext/Frappe webhook events |

### Example Chat Request

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <your-api-secret-key>" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "emp_456", "query": "How many annual leave days am I entitled to?"}'
```

### Example ERPNext Pull Sync

```bash
curl -X POST http://localhost:8000/api/v1/erpnext/sync/pull \
  -H "Authorization: Bearer <your-api-secret-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "doctypes": ["Employee"],
    "limit_per_doctype": 100
  }'
```

### Example ERPNext Webhook

Send Frappe webhook payloads to:

```text
POST /api/v1/erpnext/webhook
```

If `ERP_WEBHOOK_SECRET` is configured, include:

```text
X-Frappe-Webhook-Signature: sha256=<hex-hmac-of-raw-body>
```
