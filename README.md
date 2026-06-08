# EVA — AI Shopping Agent

EVA（E-Commerce Value Analyst）是一个基于多 Agent 协作的 AI 电商购物智能决策系统。用户以自然语言描述购物需求，系统自动完成意图分析、商品搜索、价格对比、评论分析和购买建议的全链路智能决策。

## 架构概览

```
用户 → Next.js 前端 → Nginx → FastAPI 后端 → LangGraph Agent 管线
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                 MySQL 8.4      Redis 7       Milvus 2.4
               (业务数据)    (会话缓存)    (向量知识库)
                    │
                    ▼
              7 个 LLM 提供商（并行竞速）
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 16, React 19, TypeScript, TailwindCSS v4, Zustand, Framer Motion |
| 后端 | FastAPI, Python 3.14, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| AI | LangGraph, LangChain, OpenAI, DeepSeek, GLM-4, ERNIE（7 模型） |
| 数据 | MySQL 8.4, Redis 7, Milvus 2.4 (etcd + MinIO) |
| 部署 | Docker Compose, Nginx, 多阶段构建 |

## 快速开始

### 前置要求

- Docker & Docker Compose
- OpenAI API Key（或其他 LLM 提供商的 API Key）

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 等
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

### 默认账户

| 角色 | 邮箱 | 密码 |
|------|------|------|
| 管理员 | admin@eva.com | admin123 |
| 普通用户 | user@eva.com | user123 |

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

## 项目结构

```
EVA/
├── frontend/                # Next.js 前端
│   ├── app/                 # 页面路由（App Router）
│   │   ├── assistant/       # 主对话页面
│   │   ├── admin/           # 管理后台（模型/日志/RAG/MCP）
│   │   ├── login/           # 登录页
│   │   └── ...
│   ├── components/          # 公共组件
│   ├── stores/              # Zustand 状态管理
│   ├── lib/                 # API 客户端（SSE 流式）
│   └── proxy.ts             # 路由守卫中间件
│
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── agent/           # Agent 核心模块
│   │   │   ├── graph.py     # LangGraph 状态图定义
│   │   │   ├── intent.py    # 意图分类（关键词匹配）
│   │   │   ├── search.py    # 商品搜索节点
│   │   │   ├── review.py    # 评论分析节点
│   │   │   ├── price.py     # 价格对比节点
│   │   │   ├── decision.py  # 购买决策节点
│   │   │   ├── report_agent.py  # 报告生成
│   │   │   ├── analysis_pipeline.py  # 复合管线节点
│   │   │   ├── llm_utils.py # LLM 调用工具（并行竞速+缓存+流式）
│   │   │   └── state.py     # Agent 状态定义
│   │   ├── api/v1/          # REST API 路由
│   │   ├── models/          # SQLAlchemy 数据模型
│   │   ├── schemas/         # Pydantic 请求/响应模型
│   │   ├── services/        # 业务逻辑层
│   │   ├── core/            # 基础设施（DB/LLM/JWT）
│   │   └── config.py        # 配置管理（Pydantic Settings）
│   ├── rag/                 # RAG 知识库管道
│   │   ├── loader.py        # 文档加载（JSON/CSV/TXT）
│   │   ├── chunker.py       # 递归文本分割
│   │   ├── embedder.py      # OpenAI Embedding
│   │   ├── vector_store.py  # Milvus 向量存储
│   │   ├── retriever.py     # 混合检索
│   │   └── reranker.py      # 结果重排序
│   ├── mcp_server/          # MCP Server（对外工具暴露）
│   │   ├── server.py        # JSON-RPC 协议处理
│   │   └── tools/           # 已注册的 8 个工具
│   └── alembic/             # 数据库迁移
│
├── docker/                  # Docker 辅助配置
├── docker-compose.yml       # 9 服务编排
├── nginx.conf               # Nginx 反向代理配置
└── .env.example             # 环境变量模板
```

## 核心设计

### Agent 管线

```
用户输入 → 意图分析 → 商品搜索 → 评论分析 → 综合分析（价格→决策→报告）
              │            │           │              │
              ▼            ▼           ▼              ▼
         关键词匹配    LLM生成      LLM分析       纯计算管线
          (<1ms)      3个商品      优缺点        无需LLM
```

### 多 LLM 并行竞速

不是顺序 fallback，而是同时向最多 4 个 LLM 提供商发起请求，谁先返回就用谁：

```
DeepSeek ──┐
GLM-4  ────┼── asyncio.wait(FIRST_COMPLETED) ──→ 取最快响应
ERNIE  ────┤
OpenAI ────┘
```

将最坏延迟从 ~36s 降至 ~3s。

### Token 流式推送

LLM 生成 token → asyncio.Queue → SSE → 前端逐词渲染（打字机效果），
用户无需等待完整响应即可看到 Agent 进度。

## API 概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/auth/register` | POST | 用户注册 |
| `/api/v1/auth/login` | POST | 用户登录 |
| `/api/v1/auth/refresh` | POST | 刷新令牌 |
| `/api/v1/chat/sessions` | GET/POST | 会话管理 |
| `/api/v1/chat/sessions/{id}/stream` | POST | Agent 流式对话（SSE） |
| `/api/v1/products/search` | GET | 商品搜索 |
| `/api/v1/products/{id}` | GET | 商品详情+跨平台对比 |
| `/api/v1/reports` | GET | 分析报告列表 |
| `/api/v1/favorites` | GET/POST | 收藏管理 |
| `/api/v1/profile` | GET/PUT | 个人中心 |
| `/api/v1/memory` | GET/POST | 长期记忆管理 |
| `/api/v1/admin/stats` | GET | 系统统计（管理员） |
| `/api/v1/admin/models` | GET | AI 模型状态（管理员） |
| `/api/v1/admin/logs` | GET | 实时日志（管理员） |
| `/api/v1/models` | GET | 当前用户可用模型 |

## AI 模型分层

| Tier | 模型 | 用途 |
|------|------|------|
| Admin | DeepSeek, GPT-4o | 高精度推理、多模态识别 |
| Free | GLM-4-Flash, GLM-4.7-Flash, ERNIE-Speed, ERNIE-3.5, Seedream | 日常购物助手、图像生成 |

## MCP 工具

EVA 通过 MCP Server 对外暴露以下工具（供 Claude Desktop 等外部客户端调用）：

- `search_products` — 搜索商品
- `compare_price` — 价格对比
- `analyze_reviews` — 评论分析
- `generate_report` — 生成报告
- `save_memory` — 保存记忆
- `query_memory` — 查询记忆
- `web_search` — 网络搜索
- `rag_search` — 知识库搜索

## 许可

MIT
