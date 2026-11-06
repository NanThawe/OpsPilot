# OpsPilot

> **Enterprise Procurement & Operations AI Assistant**
>
> OpsPilot is a portfolio-grade enterprise AI application for secure document processing, procurement intelligence, permission-aware retrieval, grounded RAG, agentic workflows, and human-in-the-loop approvals.

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.12-blue" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-pgvector-336791" alt="PostgreSQL + pgvector" />
  <img src="https://img.shields.io/badge/React-TypeScript-3178C6" alt="React + TypeScript" />
  <img src="https://img.shields.io/badge/LangGraph-Agentic%20Workflows-orange" alt="LangGraph" />
  <img src="https://img.shields.io/badge/Ollama-Local%20LLM-black" alt="Ollama" />
  <img src="https://img.shields.io/badge/Docker-Containerized-2496ED" alt="Docker" />
</p>

---

## Overview

OpsPilot explores how enterprise AI systems can move beyond a simple chatbot and support real operational workflows safely.

The project combines:

- secure document ingestion and access control,
- AI-assisted document classification and extraction,
- deterministic procurement validation,
- permission-aware keyword and semantic search,
- grounded RAG with source citations,
- LangGraph-based agent routing,
- human approval checkpoints before write actions,
- persistent workflow state and audit trails,
- structured observability,
- repeatable AI evaluation and regression testing,
- containerized deployment and CI.

The main engineering principle is:

> **Use AI where judgement and language are useful. Use deterministic logic where correctness, permissions, arithmetic, and workflow control matter.**

OpsPilot currently focuses on procurement and operations workflows using synthetic purchase orders, but the architecture is designed to generalize to internal enterprise document and workflow automation.

---

## Why OpsPilot

Many AI demos stop at:

```text
Upload PDF -> Ask question -> Get LLM answer
```

OpsPilot treats enterprise AI as a wider engineering problem:

```text
Documents
   ↓
Secure ingestion
   ↓
Text extraction
   ↓
AI classification
   ↓
Structured extraction
   ↓
Deterministic validation
   ↓
Human review
   ↓
Approved knowledge layer
   ↓
Keyword + semantic search
   ↓
Grounded RAG
   ↓
LangGraph agent tools
   ↓
Human-approved actions
   ↓
Audit + observability + evaluation
```

This makes the project closer to an internal AI platform than a standalone chatbot.

---

## Key Capabilities

| Capability | Implementation |
|---|---|
| Authentication | JWT authentication with Argon2 password hashing |
| Authorization | Role and department-aware access controls |
| Secure document storage | Private storage with generated paths and SHA-256 integrity checks |
| PDF ingestion | Registration, upload, validation, download, and extraction |
| Document classification | LLM-assisted classification with mandatory human review |
| Purchase order extraction | Structured AI extraction plus deterministic reconciliation |
| Financial validation | Decimal-based subtotal, tax, discount, and total validation |
| Revision history | Versioned purchase order reprocessing |
| Approval workflows | Manager/admin review with self-approval restrictions |
| Keyword search | Permission-aware PostgreSQL document search |
| Semantic search | `pgvector` + Ollama `nomic-embed-text` embeddings |
| RAG assistant | Grounded answers with source citations and abstention |
| Agentic AI | LangGraph planner with deterministic procurement tools |
| Human-in-the-loop actions | Persistent approval workflow using LangGraph checkpoints |
| Follow-up drafting | AI-generated drafts backed by verified milestone facts |
| Audit trail | Database-backed workflow events and review history |
| Observability | Structured JSON logging, request IDs, latency and tool traces |
| Evaluation | Repeatable agent, RAG, drafting, grounding and latency checks |
| Deployment | Dockerized backend, frontend and PostgreSQL stack |
| CI | Ruff, pytest, frontend lint/build and Docker build checks |

---

## Architecture

> **Architecture diagram placeholder**
>
> A detailed Excalidraw architecture diagram will be added here.

<!--
Suggested future asset:
docs/assets/opspilot-architecture.png

Replace this placeholder with:
![OpsPilot architecture](docs/assets/opspilot-architecture.png)
-->

### Logical Architecture

```text
┌───────────────────────────────┐
│        React Frontend         │
│  Documents · Search · RAG     │
│  Reviews · Agent Workflows    │
└──────────────┬────────────────┘
               │ REST
               ▼
┌───────────────────────────────┐
│        FastAPI Backend        │
│                               │
│ Auth / RBAC                   │
│ Document APIs                 │
│ Classification               │
│ Purchase Order Processing     │
│ Knowledge Search              │
│ RAG                           │
│ LangGraph Agents              │
│ Approval Workflows            │
│ Observability                 │
└───────┬─────────────┬─────────┘
        │             │
        ▼             ▼
┌──────────────────┐  ┌────────────────────┐
│ PostgreSQL       │  │ Ollama             │
│ pgvector         │  │ qwen3:4b-instruct  │
│ LangGraph State  │  │ nomic-embed-text   │
│ Audit / Reviews  │  └────────────────────┘
└──────────────────┘
```

---

## End-to-End Procurement Workflow

### 1. Secure document ingestion

Users register and upload procurement documents through protected endpoints.

The ingestion layer performs:

- extension and content-type validation,
- PDF signature and readability checks,
- file size limits,
- generated storage paths,
- SHA-256 integrity hashing,
- duplicate upload protection.

Users only see documents permitted by their department and role.

### 2. Text extraction

PDF text is extracted page by page and persisted as structured document-page records.

Each page receives a stable source reference:

```text
document:<document_uuid>:page:<page_number>
```

These references are reused throughout search, RAG, drafting, and citations.

### 3. AI-assisted classification

OpsPilot classifies documents into:

- purchase orders,
- delivery orders,
- invoices,
- contracts,
- project records,
- other.

Classification is not automatically trusted. Every prediction begins in a review state and must be approved before entering the trusted knowledge layer.

### 4. Structured purchase order extraction

Approved purchase orders are converted into structured fields such as:

```text
PO number
supplier
buyer
currency
issue date
delivery target
line items
subtotal
tax
discount
total
delivery milestones
evidence pages
```

The LLM proposes structured data, while source-text reconciliation and deterministic parsing correct important procurement fields.

### 5. Deterministic validation

Arithmetic is not delegated to the LLM.

OpsPilot uses deterministic `Decimal` calculations to validate:

```text
line totals
subtotal
discount
tax
shipping
final payable total
```

Documents are classified as:

```text
passed
flagged
needs_review
```

This allows the system to detect financial inconsistencies rather than accepting model output at face value.

### 6. Versioned reprocessing

Flagged or review-required documents can be reprocessed. Every extraction revision is retained so changes remain traceable rather than silently overwriting prior results.

### 7. Human approval

Purchase-order approval requires an authorized manager or administrator.

Controls include:

- department access enforcement,
- creator/reviewer separation,
- extraction initiator/reviewer separation,
- revision-specific approval,
- rejection and change-request states.

Only approved purchase orders enter the trusted procurement knowledge layer.

---

## Enterprise Knowledge Layer

OpsPilot provides two complementary retrieval modes.

### Keyword Search

Traditional PostgreSQL search is useful for exact identifiers such as:

```text
PO-SYN-2026-002
OPS-SCAN
Pinecrest
Batch A
Net 30
```

### Semantic Search

Document pages are chunked and embedded using:

```text
nomic-embed-text
```

Embeddings are stored in PostgreSQL through `pgvector`.

Semantic retrieval supports natural-language queries such as:

```text
When will the first delivery arrive?
```

Search results retain document ID, title, source page, similarity score, and source reference.

The same authorization rules used for normal document access also apply to semantic retrieval.

---

## Grounded RAG Assistant

The RAG layer combines semantic retrieval with structured generation using:

```text
qwen3:4b-instruct
```

The assistant is instructed to:

- answer only from retrieved evidence,
- preserve exact dates, amounts, and quantities,
- distinguish delivery targets from individual milestones,
- cite only retrieved source pages,
- ignore instructions embedded inside retrieved documents,
- abstain when evidence is insufficient.

Example:

```text
User:
When will the first delivery arrive for PO-SYN-2026-002?

OpsPilot:
Batch A is scheduled for 10 Nov 2026.

Source:
document:<uuid>:page:2
```

For unsupported questions, such as a supplier bank account not present in the source documents, the assistant abstains rather than inventing an answer.

---

## LangGraph Procurement Agent

OpsPilot includes a read-only procurement agent built with LangGraph.

The planner routes requests into:

```text
summary
first_delivery
final_delivery
delivery_schedule
knowledge
clarify
```

Example:

```text
"When is the first delivery for PO-SYN-2026-002?"
          ↓
LangGraph planner
          ↓
first_delivery
          ↓
get_delivery_milestones
          ↓
deterministically select earliest milestone
          ↓
Batch A · 10 Nov 2026
```

The LLM determines intent. Python business logic determines the actual delivery milestone.

Unsupported actions such as:

```text
Send an email to the supplier
```

are routed to `clarify` rather than executed automatically.

---

## Human-in-the-Loop Workflows

OpsPilot supports controlled write workflows.

An employee can request a procurement follow-up such as:

```text
Confirm Batch A delivery readiness.
```

The workflow:

```text
Employee request
      ↓
AI follow-up draft
      ↓
Employee review / editing
      ↓
Pending approval
      ↓
Manager / Admin decision
      ↓
LangGraph resume
      ↓
Approved follow-up creation
      ↓
Audit event
```

### Safety Controls

The model cannot directly:

- approve its own work,
- create a follow-up without human approval,
- bypass document permissions,
- execute unsupported tools.

LangGraph persistence uses PostgreSQL checkpoints so approval workflows can pause and resume across requests.

Follow-up creation is idempotent to protect against duplicate execution during retries.

---

## Verified Follow-up Drafting

For staged deliveries, OpsPilot does not allow the LLM to freely rewrite critical quantities or dates.

Instead:

1. the requested batch is detected,
2. milestone facts are extracted from the trusted source,
3. verified dates and quantities are preserved deterministically,
4. the LLM contributes operational wording,
5. the final draft is validated before it reaches the user.

This hybrid design prevents errors such as:

```text
10 cartons -> 10 rolls
```

while still allowing natural-language task generation.

---

## Evaluation

OpsPilot includes a repeatable local evaluation suite for agent and RAG behaviour.

It currently evaluates:

- agent route selection,
- deterministic tool selection,
- procurement fact accuracy,
- delivery milestone reasoning,
- RAG grounding,
- citation correctness,
- unsupported-question abstention,
- follow-up draft correctness,
- response latency.

### Latest Regression Result

```text
Runs:                 3
Executed cases:       30
Passed:               30
Failed:               0
Pass rate:            100%
Median latency:       ~1.01 s
P95 latency:          ~3.08 s
```

The first request may be slower because the local Ollama model needs to warm up.

> The current benchmark is a controlled regression suite using synthetic procurement fixtures. It should not be interpreted as a comprehensive production benchmark.

---

## Observability

OpsPilot emits structured JSON logs for technical operations.

Tracked events include:

```text
HTTP request latency
request ID
agent route
agent tool execution
RAG retrieval
RAG generation
citation validation
follow-up generation
workflow proposal
workflow decision
workflow completion
errors
```

Example:

```json
{
  "event": "agent_tool",
  "tool": "get_delivery_milestones",
  "duration_ms": 12.8,
  "success": true,
  "request_id": "..."
}
```

Sensitive content is deliberately excluded.

OpsPilot does not log:

```text
JWTs
passwords
authorization headers
raw document text
full retrieved context
confidential prompts
```

Database audit events remain separate from operational logs:

```text
Audit trail      -> who approved or changed what
Operational logs -> what happened technically and how long it took
```

---

## Security Model

### Authentication

- JWT access tokens
- Argon2 password hashing
- token expiry

### Authorization

- department-level access
- role-aware permissions
- restricted document visibility
- approved knowledge scope
- manager/admin review permissions
- self-approval prevention

### Data Handling

- private document storage
- generated storage keys
- SHA-256 file integrity checks
- restricted download endpoints
- no public document directory

### AI Safety Controls

- retrieved documents treated as untrusted data
- prompt-injection instructions inside documents ignored
- structured LLM outputs validated
- deterministic calculations for financial validation
- verified evidence references
- unsupported questions trigger abstention
- write actions require human approval

---

## Technology Stack

### Backend

```text
Python 3.12
FastAPI
SQLAlchemy
Alembic
Pydantic
PyJWT
pwdlib / Argon2
pypdf
httpx
```

### AI / Agentic AI

```text
Ollama
qwen3:4b-instruct
nomic-embed-text
LangGraph
LangGraph PostgreSQL Checkpointer
```

### Data

```text
PostgreSQL
pgvector
SQLAlchemy ORM
```

### Frontend

```text
React
TypeScript
Vite
CSS
Nginx
```

### Engineering

```text
Docker
Docker Compose
pytest
Ruff
GitHub Actions
Git
GitHub
```

---

## Repository Structure

```text
OpsPilot/
│
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── services/
│   │   └── main.py
│   ├── evals/
│   ├── migrations/
│   ├── scripts/
│   ├── tests/
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── api.ts
│   │   └── App.tsx
│   ├── Dockerfile
│   └── nginx.conf
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .dockerignore
├── compose.yaml
├── pyproject.toml
└── README.md
```

The exact structure may evolve as the project is refined.

---

## Demo

> **Demo screenshots placeholder**

<!--
Suggested future screenshots:
1. Login / document dashboard
2. Purchase order extraction and deterministic validation
3. Semantic search results
4. RAG assistant with source citation
5. LangGraph procurement agent response
6. Follow-up task drafting
7. Manager approval dashboard
8. Workflow audit history

Suggested path:
docs/assets/screenshots/
-->

### Demo Video

> **Demo video placeholder**

A short end-to-end demonstration will be added covering:

```text
Document upload
-> extraction
-> classification
-> PO validation
-> human approval
-> semantic search
-> RAG
-> LangGraph agent
-> follow-up draft
-> manager approval
-> audit trail
```

---

## Running OpsPilot

### Prerequisites

Install:

```text
Docker Desktop
Git
Ollama
```

For local development without Docker, also install:

```text
Python 3.12
Node.js
npm
```

---

## Local LLM Setup

Install the generation model:

```bash
ollama pull qwen3:4b-instruct
```

Install the embedding model:

```bash
ollama pull nomic-embed-text
```

Verify:

```bash
ollama list
```

Ensure Ollama is running before using AI features.

---

## Environment Configuration

Create a root `.env` file.

Example:

```env
DATABASE_URL=postgresql+psycopg://opspilot:opspilot_dev@localhost:5432/opspilot

JWT_SECRET_KEY=replace-with-a-secure-local-secret
ACCESS_TOKEN_EXPIRE_MINUTES=30

AI_PROVIDER=ollama
OLLAMA_MODEL=qwen3:4b-instruct
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Do not commit `.env`.

For Docker, Compose supplies container-specific database and Ollama addresses.

---

## Run with Docker

From the repository root:

```bash
docker compose build
docker compose up
```

Services:

```text
Frontend     http://localhost:3000
Backend      http://localhost:8000
Swagger      http://localhost:8000/docs
PostgreSQL   localhost:5432
```

The migration service applies Alembic migrations and initializes LangGraph checkpoint tables before the backend starts.

Stop the stack:

```bash
docker compose down
```

---

## Local Development

### Backend

Install dependencies:

```bash
python -m pip install -e ".[dev]"
```

From `backend/`:

```bash
python -m uvicorn app.main:app --reload --env-file ../.env
```

### Frontend

From `frontend/`:

```bash
npm install
npm run dev
```

Vite development server:

```text
http://localhost:5173
```

---

## Testing

### Backend

From `backend/`:

```bash
python -m ruff check app tests
python -m pytest -q tests
```

### Frontend

From `frontend/`:

```bash
npm run lint
npm run build
```

### Agent and RAG Evaluation

Set an evaluation JWT in the current shell:

```powershell
$env:OPSPILOT_EVAL_TOKEN="<token>"
```

Then:

```bash
python -m evals.run --runs 3
```

Generated evaluation reports are excluded from Git.

---

## CI

GitHub Actions validates the project on pushes and pull requests.

The CI pipeline checks:

```text
Backend
  ├── dependency installation
  ├── database migrations
  ├── LangGraph checkpoint setup
  ├── Ruff
  └── pytest

Frontend
  ├── npm ci
  ├── lint
  └── production build

Containers
  ├── backend image build
  └── frontend image build
```

AI behavioural evaluations are intentionally not part of normal CI because they require a running local Ollama model and suitable inference hardware.

---

## Example Use Cases

### Procurement

```text
Purchase orders
Invoices
Delivery orders
Supplier follow-ups
Approval tracking
```

### Operations

```text
Project records
Operational procedures
Status reporting
Document retrieval
Follow-up management
```

### Enterprise Knowledge

```text
Internal policies
Contracts
Department records
Permission-aware assistants
Source-grounded question answering
```

---

## Design Decisions

### Why local Ollama?

The project was intentionally designed to work without paid API credits.

Local inference also demonstrates:

- model abstraction,
- private document processing,
- offline evaluation,
- controlled enterprise deployment patterns.

### Why PostgreSQL + pgvector?

Using PostgreSQL for both application data and vector search keeps the MVP compact while supporting relational permissions, approval records, audit data, semantic embeddings, and transactional workflows.

### Why LangGraph?

LangGraph is used where explicit state, routing, interruption, and workflow resumption matter.

It is not used to replace deterministic business logic.

### Why human approval?

Enterprise automation should not assume that a model-generated action is authorized merely because the model proposed it.

OpsPilot separates:

```text
AI recommendation
```

from:

```text
authorized business action
```

---

## Current Limitations

OpsPilot is a portfolio MVP, not a production deployment.

Current limitations include:

- PDF extraction is primarily text-based and does not include a full OCR pipeline.
- Complex multi-column or scanned procurement tables require stronger table extraction.
- The evaluation dataset currently uses synthetic procurement fixtures.
- Ollama performance depends on local hardware.
- Authentication is application-local rather than enterprise SSO.
- Documents use local private storage rather than S3 or equivalent object storage.
- Observability is JSON-log based rather than connected to OpenTelemetry or a managed platform.
- External enterprise integrations such as CRM, ERP, email, and project-management systems are not connected.
- Production secrets management, TLS termination, backup automation, and infrastructure hardening would be required before real deployment.

These limitations are intentionally documented rather than hidden.

---

## Future Extensions

Potential next-stage improvements include:

- OCR and layout-aware document extraction,
- table extraction for complex invoices and POs,
- hybrid keyword/vector retrieval,
- reranking,
- OpenTelemetry tracing,
- enterprise SSO,
- external tool integrations,
- object storage,
- expanded prompt-injection and red-team evaluations,
- larger evaluation datasets,
- cloud deployment,
- model-provider abstraction across hosted and local LLMs.

---

## Engineering Principles Demonstrated

OpsPilot is intended to demonstrate more than model integration.

The project emphasizes:

```text
AI application engineering
backend API design
enterprise permissions
retrieval systems
structured LLM outputs
deterministic validation
agent orchestration
human-in-the-loop workflows
workflow persistence
database design
security boundaries
evaluation
observability
containerization
CI
```

The goal is to show how an AI feature can be engineered into a controlled business system rather than presented as an isolated prototype.

---

## Project Status

**Portfolio MVP: Complete**

- [x] Secure document ingestion
- [x] Authentication and RBAC
- [x] PDF extraction
- [x] AI classification
- [x] Structured purchase order extraction
- [x] Deterministic validation
- [x] Revision history
- [x] Human review
- [x] Keyword search
- [x] Semantic search with pgvector
- [x] Grounded RAG
- [x] LangGraph procurement agent
- [x] Persistent human-in-the-loop workflows
- [x] AI follow-up drafting
- [x] Audit trail
- [x] Structured observability
- [x] Agent/RAG evaluation suite
- [x] Dockerized deployment
- [x] CI pipeline

---

## Author

Built as an enterprise AI engineering portfolio project focused on:

**Agentic AI · RAG · LLM Applications · Python Backend Engineering · Enterprise Workflow Automation**

---

## Disclaimer

All procurement documents, organizations, suppliers, financial values, and operational records used in the demo are synthetic and created solely for development and evaluation.

OpsPilot is a portfolio engineering project and should not be used for production procurement decisions without additional security review, infrastructure hardening, broader testing, and organizational governance.
