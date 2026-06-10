# CLAUDE.md

## Project: EVA — AI Shopping Agent

E-commerce AI shopping decision system. Users describe shopping needs in natural language; EVA performs intent analysis, product search, price comparison, review analysis, and purchase recommendations via a multi-agent pipeline.

## Architecture

```
User → Next.js (React 19, Tailwind v4) → Nginx → FastAPI → Agent Pipeline
                                                    │
                              ┌─────────────────────┼─────────────────────┐
                              ▼                     ▼                     ▼
                           MySQL 8.4            Redis 7            Milvus 2.4
                         (business data)    (session cache)    (vector knowledge)
                              │
                              ▼
                         8 LLM Providers (parallel racing with tier-based access)
```

## Key Tech

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16.2, React 19.2, TypeScript 5, TailwindCSS v4, Zustand 5, Framer Motion 12 |
| Backend | FastAPI 0.1, Python 3.14, SQLAlchemy 2.0 (async), Pydantic v2 |
| AI | OpenAI SDK (8 providers), no LangGraph (replaced by direct async pipeline v4) |
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

## Agent Pipeline (v4)

The agent no longer uses LangGraph. `backend/app/agent/pipeline.py` contains a direct async pipeline that fuses search + review into a single LLM call (reducing round-trips from 2→1). Key modules:

- `agent/pipeline.py` — Main async shopping pipeline (replaces old StateGraph)
- `agent/llm_utils.py` — LLM call utilities: parallel racing (asyncio.wait FIRST_COMPLETED), caching, streaming
- `agent/product_templates.py` — Template matching for fast product responses (<1s)
- `agent/intent.py` — Intent classification (keyword matching, <1ms)
- `agent/state.py` — AgentState definition
- `agent/graph.py` — **Deprecated stub** (kept for backwards compat, raises RuntimeError)

### LLM Providers (8 total, tiered)

**Admin tier:** DeepSeek (primary), OpenAI GPT-4o
**Free tier:** Groq LPU, GLM-4-Flash, GLM-4.7-Flash, ERNIE-Speed, ERNIE-3.5, Seedream (image gen)

Parallel racing strategy: fire to multiple providers simultaneously, take the first successful response. Worst-case latency reduced from ~36s to ~3s.

LLM client management in `core/llm.py`:
- Shared `httpx.AsyncClient` with connection pooling
- Per-provider cached `AsyncOpenAI` clients
- Token usage tracking per user per provider
- Quota: admin=500K, free=100K tokens

## Database

- **Dev:** SQLite (`backend/eva_dev.db`, `use_sqlite=true` in config)
- **Prod:** MySQL 8.4 (`use_sqlite=false`)
- ORM: SQLAlchemy 2.0 async with `async_sessionmaker`
- Default users seeded at startup: admin@eva.com/admin123, user@eva.com/user123

## Project Structure

```
backend/app/
├── agent/          # Agent pipeline (v4 direct async)
├── api/v1/         # REST routes (auth, chat, products, reports, favorites, profile, memory, admin)
├── models/         # SQLAlchemy models (user, chat, product, report, favorite, agent_run, memory)
├── schemas/        # Pydantic request/response schemas
├── services/       # Business logic (auth, agent, memory, rag)
├── core/           # Infrastructure (database, llm, security/JWT)
└── config.py       # Pydantic Settings (reads from .env)

backend/rag/        # RAG pipeline (loader, chunker, embedder, vector_store, retriever, reranker)
backend/mcp_server/ # MCP JSON-RPC server (8 tools exposed)

frontend/app/       # Next.js App Router pages
frontend/stores/    # Zustand stores (auth, chat)
frontend/lib/       # API client with SSE streaming support
frontend/proxy.ts   # Route guard middleware
frontend/components/ # Shared React components
```

## API Routes

See README.md for full API table. Key SSE streaming endpoint:
`POST /api/v1/chat/sessions/{id}/stream` — Agent streaming dialogue

## Default Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@eva.com | admin123 |
| User | user@eva.com | user123 |

## Configuration

- Settings loaded from `.env` via Pydantic `BaseSettings`
- `.env.example` is the template (copy to `.env`)
- JWT auth with access (15min) + refresh (7d) tokens
- CORS origins configurable via `CORS_ORIGINS` env var

## Docker Deployment

9 services in `docker-compose.yml`: nginx, frontend, backend, mcp, mysql, redis, milvus, etcd, minio.
All services on internal `eva-net` network. Only nginx exposes port 80 to host.
