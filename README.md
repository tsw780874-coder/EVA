# EVA — AI Shopping Agent

> 面向电商场景的智能 AI Agent 系统，支持商品语义检索、多源数据聚合、智能推荐决策与结构化购物分析。

[![Python](https://img.shields.io/badge/Python-3.13+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16.2-black)](https://nextjs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## ✨ Core Features

- 🧠 **电商意图识别** — 9 类购物意图分类，87 个电商语义关键词，毫秒级路由
- 🔍 **商品语义检索** — 跨数据源混合检索（向量 + BM25），Rerank 重排序
- 📊 **多维商品分析** — 价格分布、参数对比、评价摘要、店铺信誉
- 🧾 **RAG 商品知识库** — 结构化商品文档 + FAQ + 购买指南的向量化问答
- 🧩 **Function Calling 工具系统** — LLM 驱动的搜索、比价、推荐、计算工具链
- 🧠 **用户画像 Memory** — 短期会话记忆 + 长期偏好记忆 + 向量语义检索（L1/L2/L3）
- 🤖 **ReAct 推理循环** — Plan → Act → Observe，最多 3 步推理链
- ⚡ **SSE 流式输出** — Token 级流式渲染，首 token 延迟 <500ms
- 🛡️ **反幻觉机制** — 数据质量门禁 + 验证门（前置阻断）+ 6 维幻觉检测
- 🔌 **MCP Server** — STDIO + SSE 双 transport，8 工具 JSON-RPC 暴露

---

## 🏗 Architecture

```
User Query
    │
    ▼
┌──────────────────┐
│  Intent Router    │  9 types, 87 keywords, <1ms
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  Content Filter   │  Input sanitization + Injection detection
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  LLM Tool Planner │  Function Calling → tool selection
└──────┬───────────┘
       │
       ▼
┌──────────────────────────────┐
│     Execution Layer          │
│  ┌────────────────────────┐ │
│  │  Parallel Search (5+)  │ │  Official APIs → SerpAPI → RAG → Cache
│  │  Platform Adapters     │ │
│  └────────────────────────┘ │
│  ┌────────────────────────┐ │
│  │  Tool Executor (8)     │ │  ReAct loop: think→act→observe
│  │  Semaphore(8), timeout │ │
│  └────────────────────────┘ │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────┐
│  RAG + Memory     │  Milvus vector search + user preferences
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Verification Gate │  4-dimension check → BLOCK/FLAG/ALLOW
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  LLM Synthesis    │  6-provider parallel racing, FIRST_COMPLETED
└──────┬───────────┘
       │
       ▼
  Final Answer (SSE/WebSocket)
```

---

## 🧰 Tech Stack

| 层级 | 技术 |
|------|------|
| **LLM** | DeepSeek · GPT-4o · Gemini · Groq LPU · GLM-4 · ERNIE — 8 provider 统一访问 |
| **Agent** | 自研异步管道（无 LangGraph 依赖）— ReAct 循环 + Function Calling + Circuit Breaker |
| **Backend** | FastAPI · Python 3.13+ · SQLAlchemy 2.0 (async) · Pydantic v2 |
| **Frontend** | Next.js 16 · React 19 · TypeScript 5 · TailwindCSS v4 · Zustand · Framer Motion |
| **Vector DB** | Milvus 2.4 — 1536-dim, IVF_FLAT index |
| **Search** | BM25 + Vector 混合检索 · Reranker (freshness + keyword + LLM) |
| **Cache** | Redis 7 + in-memory fallback · Semantic cache (3-level) |
| **Database** | MySQL 8.4 (prod) / SQLite (dev) |
| **Deploy** | Docker Compose · Nginx reverse proxy |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.13+ · Node.js 20+ · Docker (optional)
- 至少一个 LLM API Key

### 1. Clone & Config

```bash
git clone https://github.com/tsw780874-coder/EVA.git
cd EVA
cp .env.example .env
# 编辑 .env —— 至少填入一个 LLM API Key
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

验证: `curl http://localhost:8000/health` → `{"status":"ok"}`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:3000`

### 4. Docker (一键)

```bash
docker-compose up -d
```

### Default Accounts

| Role | Email | Password | Quota |
|------|-------|----------|-------|
| Admin | admin@eva.com | admin123 | Unlimited |
| User | user@eva.com | user123 | 20/day |

---

## 💡 How It Works

### 示例 1：商品检索

```
User: "推荐一款办公笔记本"
  ↓
Intent Router → buy_product (95%)
  ↓
Tool Planner → calls product_search tool
  ↓
Parallel Search → 5 layers × 3 products returned
  ↓
Verification Gate → evidence check PASS (3 sources)
  ↓
LLM Synthesis → SSE streaming → structured product cards
```

### 示例 2：多工具组合（ReAct 推理）

```
User: "3000-5000预算，性价比最高的移动办公设备"
  ↓
Intent → recommend_products
  ↓
Step 1: product_search → 15 candidates
  ↓ observe: prices 2000-8000, need filter
Step 2: price_filter(3000-5000) → 7 candidates
  ↓ observe: need value ranking  
Step 3: ranking(sort=value) → Top 3
  ↓
Verification → cross-validate prices → ALLOW
  ↓
Final Report: comparison table + recommendation + reasons
```

---

## 🔧 Tools System

Agent 通过 OpenAI Function Calling 协议调用工具，支持 ReAct 循环。

```
Tool Registry (8 tools)
├── product_search    — 跨源商品语义检索
├── price_compare     — 多源价格对比
├── price_filter      — 价格区间过滤
├── ranking           — 多维排序与重打分
├── review_analyze    — 评价摘要分析
├── rag_search        — 商品知识库问答
├── memory_query      — 用户记忆查询
└── compute           — 统计计算与预算规划（含沙箱 custom_calc）
```

### Function Calling Schema (例)

```json
{
  "name": "product_search",
  "description": "跨数据源语义检索商品，返回结构化结果",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "top_k": {"type": "integer", "default": 5}
    },
    "required": ["query"]
  }
}
```

---

## 🛡️ Anti-Hallucination

三层门禁确保输出可信：

| 门禁 | 职责 | 行为 |
|------|------|------|
| **DataQualityGate** | 商品数据入口过滤 | 拦截 source=simulated/template，price=0 仅标注不拦截 |
| **VerificationGate** | 回答发布前验证（4 维检查） | BLOCK → SAFE_FALLBACK / FLAG → 附加警告 / ALLOW → 正常输出 |
| **HallucinationGuard** | 6 维幻觉检测 | 标注警告，不阻断（由 VerificationGate 统一判定） |

**核心原则**: 有证据 → 放行；零证据 → 拦截。不会阻止外部真实数据返回。

---

## 📚 RAG & Memory

### RAG Pipeline

```
Documents → Chunker (recursive split, 512 tokens)
         → Embedder (text-embedding-3-small, 1536-dim)
         → Milvus (IVF_FLAT, IP metric)
         → Hybrid Search (BM25 + Vector, RRF fusion)
         → Reranker (freshness decay + keyword + LLM)
```

### Memory System (L1/L2/L3)

| 层级 | 存储 | TTL | 用途 |
|------|------|-----|------|
| L1 Short-term | Redis session | 24h | 对话上下文 |
| L2 Long-term | MySQL | permanent | 用户偏好、已确认事实、自动摘要 |
| L3 Retrieval | Milvus vector | permanent | 语义记忆检索 |

对话结束后 LLM 自动提取用户偏好和决策，存入 L2+L3 记忆。

---

## 📁 Project Structure

```
EVA/
├── backend/
│   ├── app/
│   │   ├── agent/              # Agent 核心
│   │   │   ├── pipeline.py             # 多层级并行搜索管道
│   │   │   ├── intent_router.py        # 意图分类 + 路由
│   │   │   ├── model_router.py         # 智能模型路由
│   │   │   ├── llm_utils.py            # LLM 调用（竞速+流式+Function Calling）
│   │   │   ├── platform_adapters/      # 数据源适配器
│   │   │   ├── real_commerce_engine.py # 数据质量门禁+决策引擎
│   │   │   └── eva_system_prompt.py    # 系统提示词+多风格输出
│   │   ├── tools/               # 工具系统（8 tools, registry + executor）
│   │   ├── hybrid/              # 多源情报层（guard, reasoner, resolver）
│   │   ├── core/                # 基础设施
│   │   │   ├── circuit_breaker.py      # 模型熔断器
│   │   │   ├── rate_limiter.py         # 滑动窗口限流
│   │   │   ├── content_filter.py       # 输入安全过滤
│   │   │   └── verification_gate.py    # 验证门（前置阻断）
│   │   ├── api/v1/              # REST API
│   │   ├── models/              # 数据模型
│   │   └── services/            # 业务逻辑
│   ├── rag/                     # RAG 管道
│   ├── mcp_server/              # MCP Server (STDIO + SSE, 8 tools)
│   ├── tests/                   # 测试套件 (81 pass / 0 fail)
│   └── knowledge/               # 知识库源文件
├── frontend/
│   ├── app/assistant/           # AI 对话页面（含商品对比）
│   ├── stores/                  # Zustand 状态管理
│   ├── components/              # 共享组件
│   └── lib/                     # API 客户端 (SSE + WebSocket)
├── docker-compose.yml
└── .env.example
```

---

## ⚡ Performance

### Latency Targets

| 场景 | 目标 | 实测 |
|------|------|------|
| 意图分类 | <1ms | <1ms |
| 语义缓存命中 | <10ms | <10ms |
| RAG 商品检索 | <500ms | 100-500ms |
| LLM 首 token | <500ms | 200-900ms (6-provider 竞速) |
| 完整购物分析 | <10s | 0.5-3s |

### Optimizations

- **6-provider 真并行竞速** — `asyncio.wait(FIRST_COMPLETED)`, 最快响应即返回
- **5 层并行搜索** — 所有数据源同时启动
- **Circuit Breaker** — 连续 3 次失败自动熔断，30s 后半开探测
- **双层缓存** — Redis + in-memory fallback, TTL 分层
- **连接池** — httpx(50) + SQLAlchemy(20) + Milvus(4 workers)
- **Token 队列** — 256 容量异步队列，40ms 轮询

---

## 🔌 MCP Server

8 工具通过 JSON-RPC 暴露，支持 STDIO + SSE 双 transport：

```bash
# SSE transport
curl http://localhost:8000/mcp/health
# → {"status":"ok","tools_count":8,"transports":["stdio","sse"]}

# STDIO transport
python mcp_server/server.py
```

---

## 🧪 Testing

```bash
cd backend
PYTHONPATH=. python tests/test_suite.py
```

```
WHITE-BOX   55 pass / 0 fail   (imports, logic, state machines, config)
BLACK-BOX   26 pass / 0 fail   (all API endpoints)
E2E          7 pass / 0 fail   (full SSE chat pipeline)
─────────────────────────────────
TOTAL       81 pass / 0 fail
```

---

## 🛣️ Roadmap

- [x] 多轮对话 Agent + 多模型并行竞速
- [x] Function Calling + ReAct 推理循环
- [x] RAG 商品知识库 + 混合检索
- [x] 用户画像 Memory (L1/L2/L3)
- [x] SSE/WebSocket 流式输出
- [x] 验证门 + 数据质量门禁（反幻觉）
- [x] Circuit Breaker 熔断 + Rate Limiting
- [x] MCP Server (STDIO + SSE)
- [x] 前端商品对比 UI
- [ ] 多 Agent 协作推荐
- [ ] 商品趋势预测
- [ ] 可视化推荐解释
- [ ] 插件化工具市场

---

## 📄 License

MIT
