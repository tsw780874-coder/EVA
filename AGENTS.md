# AGENTS.md

## Project: EVA — AI Shopping Agent

E-commerce AI shopping decision system. Users describe shopping needs in natural language; EVA performs intent analysis, product search, price comparison, review analysis, and purchase recommendations via a multi-agent pipeline.

## Architecture

```
User → Next.js (React 19, Tailwind v4) → Nginx → FastAPI → Agent Pipeline
                                                    │
                              ┌─────────────────────┼─────────────────────┐
                              ▼                     ▼                     ▼
                           MySQL 8.4            Redis 7            Milvus 2.4
                         (business data)    (dual-layer cache)   (vector knowledge)
                              │
                              ▼
                         8 LLM Providers (true parallel racing + circuit breaker)
                              │
                              ▼
                    Platform Adapters (official API → SerpAPI → cache fallback)
```

## Key Tech

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16.2, React 19.2, TypeScript 5, TailwindCSS v4, Zustand 5, Framer Motion 12 |
| Backend | FastAPI, Python 3.13+, SQLAlchemy 2.0 (async), Pydantic v2 |
| AI | OpenAI SDK (8 providers), true parallel racing, Function Calling, Circuit Breaker |
| Search | 5-layer parallel search, hybrid search (BM25+Milvus), product knowledge graph |
| Trust | RAG knowledge base, Verification Gate (pre-publish blocking), anti-hallucination guard |
| Data | MySQL 8.4, Redis 7, Milvus 2.4 (+ etcd + MinIO) |
| Deploy | Docker Compose (9 services), Nginx reverse proxy |

## Dev Commands

```bash
# Backend (from EVA/backend/)
uvicorn app.main:app --reload --port 8000

# Or with explicit venv:
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# Frontend (from EVA/frontend/)
npm run dev    # Next.js dev server on port 3000
npm run build  # Production build
```

## Agent Pipeline

Key modules:

- `agent/pipeline.py` — Main async pipeline (multi-layer parallel search)
- `agent/llm_utils.py` — LLM utilities: true parallel racing, caching, streaming, Function Calling
- `agent/intent_router.py` — Intent classification (<1ms, 9 types)
- `agent/model_router.py` — Complexity-based model routing
- `agent/real_commerce_engine.py` — Data quality gate + shopping decision engine
- `agent/eva_system_prompt.py` — System prompt + multi-style output
- `agent/progressive_context.py` — Progressive context builder
- `agent/platform_adapters/` — Platform API adapters (JD/Taobao/PDD/SerpAPI)

### Infrastructure

- `core/circuit_breaker.py` — Model circuit breaker (3 failures → OPEN, 30s → HALF_OPEN)
- `core/rate_limiter.py` — Sliding window rate limiter
- `core/content_filter.py` — Input sanitization + prompt injection detection
- `core/verification_gate.py` — Pre-publish 4-dimension verification

## Project Structure

```
backend/app/
├── agent/              # Agent pipeline
│   ├── platform_adapters/  # Data source adapters
├── api/v1/             # REST routes
├── models/             # SQLAlchemy models
├── schemas/            # Pydantic schemas
├── services/           # Business logic
├── tools/              # Tool system (8 tools, registry + executor)
├── hybrid/             # Multi-source intelligence layer
├── core/               # Infrastructure
└── config.py           # Settings

backend/rag/            # RAG pipeline
backend/mcp_server/     # MCP Server (STDIO + SSE, 8 tools)

frontend/app/           # Next.js App Router
frontend/stores/        # Zustand stores
frontend/lib/           # API client (SSE)
frontend/proxy.ts       # Route guard
frontend/components/    # Shared components
```

## API Routes

- `POST /api/v1/chat/sessions/{id}/stream` — Agent SSE streaming
- `POST /api/v1/chat/sessions/{id}/stream/hybrid` — Hybrid AI streaming
- `GET /api/v1/chat/sessions/{id}/ws` — WebSocket endpoint
- `GET /mcp/health` — MCP server health
- `GET /admin/breakers` — Circuit breaker states

## Default Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@eva.com | admin123 |
| User | user@eva.com | user123 |

## Configuration

- Settings from `.env` via Pydantic `BaseSettings`
- `.env.example` is the template
- JWT: access 15min + refresh 7d
- Platform API keys for JD Union, Taobao Alliance, PDD Duoduo Alliance
