# EVA — AI Shopping Agent

EVA（E-Commerce Value Analyst）是一个企业级 AI 电商购物智能决策系统。用户以自然语言描述购物需求，系统通过 RAG 知识库检索真实数据，结合多 LLM 并行竞速，自动完成意图分析、商品搜索、价格对比和购买建议的全链路智能决策。

> **v8 核心升级：** 并行搜索 (Fast Mode)，5 层搜索策略，验证门 (Verification Gate)，产品知识图谱，渐进式上下文。

## 架构概览

```
用户 → Next.js 前端 → FastAPI 后端 → v6 Agent 管线 (v8 Fast Mode)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
     MySQL 8.4           Redis 7           Milvus 2.4
   (业务数据)          (双层缓存)        (向量知识库)
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
                    8 个 LLM 提供商
                (智能路由 + 并行竞速)
                            │
                            ▼
                    验证门 (Verification Gate)
                            │
                            ▼
                    引用 + 可信度评分
```

### v8 Fast Mode Pipeline

```
User → Intent → Layer 0+1+2 并行搜索 → Layer 3 别名 → Layer 4 全网 → 验证门 → 报告
                       │                          │
                  模板+Wiki+图谱              实时搜索回退
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 16.2, React 19.2, TypeScript 5, TailwindCSS v4, Zustand 5, Framer Motion 12 |
| 后端 | FastAPI, Python 3.14, SQLAlchemy 2.0 (async), Pydantic v2 |
| AI | 8 LLM 提供商，智能模型路由，并行竞速，流式输出 |
| 搜索 | 5 层搜索策略，混合搜索 (BM25+Milvus)，产品知识图谱，别名匹配 |
| 可信度 | RAG 知识库，验证门 (Verification Gate)，引用追踪，置信度分层 |
| 数据 | MySQL 8.4, Redis 7, Milvus 2.4 (+ etcd + MinIO) |
| 部署 | Docker Compose (9 服务), Nginx 反向代理 |

## 快速开始

### 前置要求

- Docker & Docker Compose
- 至少一个 LLM 提供商的 API Key

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 API Keys
```

### 2. 启动所有服务

```bash
docker-compose up -d
```

服务启动后：
- 前端：http://localhost:3000
- 后端 API：http://localhost:8000/api/v1
- 健康检查：http://localhost:8000/health
- MCP Server：http://localhost:8001/mcp

### 3. 本地开发

**后端：**

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**前端：**

```bash
cd frontend
npm install
npm run dev
```

### 4. 导入知识库（RAG）

首次运行后，通过管理后台导入知识库：

```
Admin → RAG 管理 → 导入目录: backend/knowledge/
```

包含：
- `products/` — 商品数据（5 个真实商品）
- `ecommerce_rules/` — 平台政策
- `faq/` — 常见购物问答

## 项目结构

```
EVA/
├── frontend/                    # Next.js 前端
│   ├── app/                     # 页面路由（App Router）
│   │   ├── assistant/           # 主对话页面
│   │   ├── admin/               # 管理后台
│   │   │   ├── agents/          # Agent 管理
│   │   │   ├── logs/            # 日志查看
│   │   │   ├── mcp/             # MCP 工具管理
│   │   │   ├── models/          # 模型状态
│   │   │   └── rag/             # RAG 知识库管理
│   │   ├── login/register/      # 认证页面
│   │   ├── product/[id]/        # 商品详情页
│   │   ├── favorites/           # 收藏夹
│   │   ├── reports/             # 购物报告
│   │   ├── profile/             # 个人中心
│   │   └── settings/            # 设置页面
│   ├── components/              # 公共组件 (AuthGuard)
│   ├── stores/                  # Zustand 状态管理 (authStore, chatStore)
│   ├── lib/                     # API 客户端 (SSE 流式)
│   └── proxy.ts                 # 路由守卫中间件
│
├── backend/
│   ├── app/
│   │   ├── agent/               # Agent 核心 (19 模块)
│   │   │   ├── pipeline.py              # 主管线 (v6 + v8 Fast Mode)
│   │   │   ├── intent_router.py         # 意图分类 + 路由
│   │   │   ├── model_router.py          # 智能模型路由
│   │   │   ├── llm_utils.py             # LLM 调用（竞速+流式+缓存）
│   │   │   ├── product_db.py            # 产品数据库
│   │   │   ├── product_graph.py         # 产品知识图谱
│   │   │   ├── product_wiki.py          # 产品维基检索
│   │   │   ├── product_templates.py     # 模板匹配（<1ms）
│   │   │   ├── product_alias_db.py      # 产品别名匹配
│   │   │   ├── product_cache.py         # 产品缓存层
│   │   │   ├── product_validator.py     # 产品数据验证
│   │   │   ├── query_rewriter.py        # 查询重写
│   │   │   ├── live_search.py           # 实时搜索
│   │   │   ├── similar_search.py        # 相似商品搜索
│   │   │   ├── hot_products.py          # 热门商品
│   │   │   ├── trending_searches.py     # 趋势搜索
│   │   │   ├── popularity_scorer.py     # 流行度评分
│   │   │   ├── confidence_tiers.py      # 置信度分层
│   │   │   └── progressive_context.py   # 渐进式上下文
│   │   ├── api/v1/              # REST API 路由
│   │   ├── models/              # SQLAlchemy 数据模型
│   │   ├── schemas/             # Pydantic 请求/响应模型
│   │   ├── services/            # 业务逻辑层
│   │   ├── core/                # 基础设施
│   │   │   ├── llm.py                   # LLM 客户端管理 (8 模型)
│   │   │   ├── database.py              # 异步数据库引擎
│   │   │   ├── security.py              # JWT 认证
│   │   │   ├── verifier.py              # 数据验证器
│   │   │   ├── verification_gate.py     # 验证门 (v8)
│   │   │   ├── citations.py             # 引用追踪
│   │   │   ├── confidence.py            # 可信度评分
│   │   │   └── perf.py                  # 性能计时器
│   │   └── cache/
│   │       └── redis_cache.py           # Redis+内存双层缓存
│   ├── rag/                     # RAG 知识库管道
│   │   ├── hybrid_search.py             # BM25 + 向量混合搜索
│   │   ├── reranker.py                  # 重排序（含新鲜度衰减）
│   │   ├── retriever.py                 # 向量检索
│   │   ├── embedder.py                  # OpenAI Embedding
│   │   ├── vector_store.py              # Milvus 向量存储
│   │   ├── chunker.py                   # 递归文本分割
│   │   └── loader.py                    # 知识库加载器
│   ├── knowledge/               # 知识库源文件
│   │   ├── products/                    # 商品数据 (Markdown)
│   │   ├── ecommerce_rules/             # 平台政策
│   │   └── faq/                         # 常见问答
│   ├── mcp_server/              # MCP Server (8 工具)
│   └── tests/                   # 测试套件
│       ├── test_blackbox.py             # 黑盒测试 (API)
│       └── test_whitebox.py             # 白盒测试 (模块)
│
├── docker-compose.yml           # 9 服务编排
├── nginx.conf                   # Nginx 反向代理
└── .env.example                 # 环境变量模板
```

## 核心设计

### 5 层搜索策略 (v6 + v8 Fast Mode)

| 层级 | 名称 | 策略 | 延迟 |
|------|------|------|------|
| Layer 0 | 模板匹配 | 热门商品模板直接命中 | <1ms |
| Layer 1 | 产品 Wiki | 向量检索产品知识库 | ~100ms |
| Layer 2 | 知识图谱 | 产品关系图遍历 | ~50ms |
| Layer 3 | 别名匹配 | 品牌+型号别名扩展 | <10ms |
| Layer 4 | 实时搜索 | 全网实时数据回退 | ~2s |

**v8 Fast Mode：** Layer 0 + Layer 1 + Layer 2 并行执行，取首个命中结果，最坏延迟降至 ~100ms。

```python
# 配置管线模式（.env）
PIPELINE_MODE=fast    # v8 并行模式（默认）
PIPELINE_MODE=legacy  # v6 串行模式
```

### 验证门 (Verification Gate, v8)

```
产品候选 → 价格验证 → 参数验证 → 时效检查 → 通过 / 驳回+重新搜索
```

- 验证价格在合理范围内
- 交叉检查关键参数一致性
- 过期数据自动驳回触发重新搜索

### 智能模型路由

```python
route_query("你好")          → Groq LPU (~400ms)   # 简单聊天
route_query("iPhone价格")    → Groq→DeepSeek         # 购物查询
route_query("详细对比分析...") → DeepSeek→GPT-4o      # 复杂分析
```

### 多 LLM 并行竞速

```
Groq LPU ───┐
GLM-4  ─────┼── asyncio.wait(FIRST_COMPLETED) ──→ 取最快响应
DeepSeek ───┤
OpenAI ─────┘
```

### 流式输出

LLM 生成 token → asyncio.Queue → SSE → 前端逐词渲染（打字机效果）

### 可信度体系

| 组件 | 功能 |
|------|------|
| VerificationGate | 产品验证门，数据核验 |
| Verifier | 交叉验证价格/参数/评价 |
| CitationTracker | 追踪每项数据来源 |
| ConfidenceScorer | 计算 0-100% 可信度 |
| ConfidenceTiers | 分层置信度（高/中/低） |
| Hybrid Search | BM25 + 向量提升召回率 |
| Freshness Decay | 过期数据自动降权 |

### 反幻觉原则

- ✅ "只使用提供的知识库内容"
- ✅ "如果知识库内容不足，明确告知"
- ✅ "不要在回答中编造具体价格"
- ❌ ~~"生成3个商品"~~ (已移除)

## API 概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/auth/register` | POST | 用户注册 |
| `/api/v1/auth/login` | POST | 用户登录 |
| `/api/v1/auth/refresh` | POST | 刷新令牌 |
| `/api/v1/chat/sessions` | GET/POST | 会话管理 |
| `/api/v1/chat/sessions/{id}/stream` | POST | Agent 流式对话 (SSE) |
| `/api/v1/products/search` | GET | 商品搜索 |
| `/api/v1/products/{id}` | GET | 商品详情+跨平台对比 |
| `/api/v1/reports` | GET | 分析报告列表 |
| `/api/v1/favorites` | GET/POST/DELETE | 收藏管理 |
| `/api/v1/profile` | GET/PUT | 个人中心 |
| `/api/v1/memory` | GET/POST | 长期记忆管理 |
| `/api/v1/models` | GET | 可用 AI 模型 |
| `/api/v1/admin/stats` | GET | 系统统计（管理员） |
| `/api/v1/admin/models` | GET | AI 模型状态 |
| `/api/v1/admin/models/verify` | GET | 验证模型可用性 |
| `/api/v1/admin/rag` | GET | RAG 知识库状态 |

### SSE 事件类型 (流式对话)

| 事件类型 | 说明 |
|---------|------|
| `agent_start` | Agent 启动确认 |
| `agent_progress` | 管线进度更新 |
| `token` | Token 级流式文本 |
| `agent_result` | 商品搜索结果（含 source/confidence 字段） |
| `final_report` | 最终分析报告 |
| `trust` | 可信度元数据 |
| `perf` | 性能耗时分解 |
| `done` | 流完成 |

## AI 模型分层

| Tier | 模型 | 用途 |
|------|------|------|
| Admin | DeepSeek, GPT-4o | 高精度推理、多模态识别 |
| Free | Groq LPU, GLM-4-Flash, GLM-4.7-Flash, ERNIE-Speed, ERNIE-3.5, Seedream | 快速响应、日常助手、图像生成 |

## MCP 工具

- `search_products` — 搜索商品
- `compare_price` — 价格对比
- `analyze_reviews` — 评论分析
- `generate_report` — 生成报告
- `save_memory` — 保存记忆
- `query_memory` — 查询记忆
- `web_search` — 网络搜索
- `rag_search` — 知识库搜索

## 性能指标

| 场景 | 目标 | 实测 |
|------|------|------|
| 普通聊天 | <1s 首 token | 400-900ms |
| RAG 商品检索 | <2s | 100-500ms |
| 模板匹配 (Layer 0) | <1ms | <1ms |
| v8 Fast Mode | <200ms | ~100ms |
| 购物分析报告 | <10s | 0.1-2s |

## 测试

```bash
# 白盒测试（模块逻辑）
cd backend
python tests/test_whitebox.py

# 黑盒测试（API 端点）
python tests/test_blackbox.py
```

测试通过率：白盒 96.4% / 黑盒 88.6%

## 默认账户

| 角色 | 邮箱 | 密码 |
|------|------|------|
| 管理员 | admin@eva.com | admin123 |
| 普通用户 | user@eva.com | user123 |

## 版本历史

| 版本 | 核心变更 |
|------|---------|
| v8 | 验证门 (Verification Gate)，Fast Mode 并行搜索 (L0+L1+L2)，产品知识图谱，渐进式上下文 |
| v7 | 5 层搜索策略，产品别名匹配，相似搜索，实时搜索回退，置信度分层 |
| v6 | 多层级搜索管线，产品 Wiki，热门商品，趋势搜索，查询重写 |
| v5 | RAG-First 架构，反幻觉体系，数据验证层，引用机制，可信度评分，混合搜索，知识库 |
| v4 | 智能模型路由，Redis 双层缓存，性能计时，流式优化，对话摘要 |
| v3 | 直接异步管线（替代 LangGraph），并行竞速，模板匹配 |
| v2 | LLM 连接池，多模型验证，token 用量追踪 |
| v1 | 初始版本：FastAPI + Next.js + LangGraph Agent |

## 许可

MIT
