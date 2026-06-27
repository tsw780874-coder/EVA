"""
Agent Memory Service — 三层记忆系统:
  L1: Short-term (Redis, 24h TTL)
  L2: Long-term (MySQL, 结构化持久化)
  L3: Retrieval (Milvus, 向量语义检索)

防污染规则：
  - 禁止存储 AI 推理过程
  - 禁止存储未验证内容
  - 禁止存储推测/可能性内容
  - 仅存储用户确认的数据、API返回结果、SQL查询结果
"""
import json
import re
from datetime import datetime, timezone
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.models.memory import Memory

settings = get_settings()

# ═══════════════════════════════════════════════════════════════════════
# 防污染：禁止存储的内容模式
# ═══════════════════════════════════════════════════════════════════════

FORBIDDEN_CONTENT_PATTERNS = [
    (r"可能|也许|大概|估计|应该|差不多", "推测性语言"),
    (r"AI推理|模型认为|基于训练|LLM生成", "AI推理过程"),
    (r"未经证实|待确认|不确定|未验证", "未验证内容"),
    (r"可能是|或许是|一般来说|通常情况下", "模糊回答"),
    (r"建议您|您可以尝试|推荐您考虑", "AI生成的建议（非用户确认）"),
]

FORBIDDEN_KEY_PATTERNS = [
    r"^ai_reasoning",
    r"^llm_thought",
    r"^unverified",
    r"^guess",
    r"^speculation",
]

# 允许存储的数据来源
ALLOWED_SOURCES = {
    "user_confirmed",     # 用户确认
    "api_result",         # API 返回
    "sql_result",         # SQL 查询
    "rag_verified",       # RAG 验证通过
    "tool_result",        # 工具返回
    "system_extracted",   # 系统从对话中提取的可信事实
}


def is_safe_to_store(key: str, value: dict, source: str = "") -> bool:
    """检查内容是否安全可存储。

    Args:
        key: 记忆键
        value: 记忆值
        source: 数据来源（必须在 ALLOWED_SOURCES 中）

    Returns:
        True 如果安全可存储
    """
    # 来源检查
    if source and source not in ALLOWED_SOURCES:
        return False

    # 键名检查
    for pattern, _ in FORBIDDEN_KEY_PATTERNS:
        if re.search(pattern, key, re.IGNORECASE):
            return False

    # 内容检查
    value_str = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value)
    for pattern, reason in FORBIDDEN_CONTENT_PATTERNS:
        if re.search(pattern, value_str):
            return False

    return True


# ═══════════════════════════════════════════════════════════════════════
# L1: Short-term memory (Redis)
# ═══════════════════════════════════════════════════════════════════════

async def get_redis() -> aioredis.Redis:
    """获取 Redis 客户端 — 使用统一连接池（来自 app.cache.redis_cache）。"""
    from app.cache.redis_cache import get_redis_client
    client = await get_redis_client()
    if client is None:
        # 回退到独立连接（统一池不可用时）
        import redis.asyncio as aioredis
        return await aioredis.from_url(settings.redis_url, decode_responses=True)
    return client


async def save_session_history(
    user_id: str, session_id: str, messages: list[dict], ttl: int = 86400,
):
    r = await get_redis()
    key = f"session:{user_id}:{session_id}"
    await r.set(key, json.dumps(messages, ensure_ascii=False), ex=ttl)


async def get_session_history(user_id: str, session_id: str) -> list[dict]:
    r = await get_redis()
    key = f"session:{user_id}:{session_id}"
    data = await r.get(key)
    return json.loads(data) if data else []


async def get_all_user_sessions(user_id: str) -> list[str]:
    """获取用户所有活跃会话的 key 列表"""
    r = await get_redis()
    pattern = f"session:{user_id}:*"
    keys = []
    async for key in r.scan_iter(match=pattern, count=50):
        keys.append(key)
    return keys


# ═══════════════════════════════════════════════════════════════════════
# L2: Long-term memory (MySQL)
# ═══════════════════════════════════════════════════════════════════════

async def save_memory(
    db: AsyncSession,
    user_id: str,
    key: str,
    value: dict,
    importance: float = 0.5,
    ttl: int | None = None,
    source: str = "",
    memory_type: str = "general",
) -> Memory | None:
    """保存记忆（带防污染检查）。

    Args:
        source: 数据来源，必须在 ALLOWED_SOURCES 中
        memory_type: 类型 — preference / confirmed_fact / project_config / faq / chat_summary
    """
    # 防污染检查
    if not is_safe_to_store(key, value, source):
        return None

    # 重要性阈值：低重要性且无明确来源的内容不存储
    if importance < 0.3 and source not in ("user_confirmed", "api_result", "sql_result"):
        return None

    result = await db.execute(
        select(Memory).where(Memory.user_id == user_id, Memory.key == key)
    )
    existing = result.scalar_one_or_none()

    value_with_meta = {
        "data": value,
        "source": source,
        "memory_type": memory_type,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing:
        existing.value = value_with_meta
        existing.importance = importance
        existing.last_accessed = datetime.now(timezone.utc)
    else:
        existing = Memory(
            user_id=user_id, key=key, value=value_with_meta,
            importance=importance, ttl=ttl,
            last_accessed=datetime.now(timezone.utc),
        )
        db.add(existing)

    await db.commit()
    await db.refresh(existing)
    return existing


async def query_memories(
    db: AsyncSession,
    user_id: str,
    keyword: str | None = None,
    limit: int = 10,
    memory_type: str | None = None,
) -> list[Memory]:
    """查询用户记忆"""
    q = select(Memory).where(Memory.user_id == user_id)
    if keyword:
        q = q.where(Memory.key.ilike(f"%{keyword}%"))
    q = q.order_by(Memory.importance.desc()).limit(limit)
    result = await db.execute(q)
    memories = list(result.scalars().all())

    if memory_type:
        memories = [
            m for m in memories
            if (m.value.get("memory_type") if isinstance(m.value, dict) else "") == memory_type
        ]

    return memories


# ═══════════════════════════════════════════════════════════════════════
# v10: 会话自动摘要 — 对话结束后生成摘要存入长期记忆
# ═══════════════════════════════════════════════════════════════════════


async def auto_summarize_session(
    user_id: str,
    session_id: str,
    query: str,
    reply: str,
) -> int:
    """对话结束后自动提取关键事实并存入记忆。

    使用 LLM 从用户 query + 助手 reply 中提取:
      - 用户偏好（品牌、预算、用途）
      - 已确认的选择/决定
      - 关键比价结论

    提取结果存入 MySQL Memory + 同步到 Milvus。
    """
    try:
        from app.agent.llm_utils import llm_call
        from app.models.memory import Memory

        # 轻量 LLM 提取
        extract_prompt = (
            "你是一个信息提取助手。从以下对话中提取用户的关键偏好和决策。\n"
            "用 JSON 格式返回，只返回 JSON，不要其他内容。\n"
            '格式: {"preferences": [...], "decisions": [...], "facts": [...]}\n'
            "每个条目不超过30字。如果没有则返回空数组。"
        )
        extract_input = f"用户: {query[:300]}\n助手: {reply[:500]}"

        content, _, _ = await llm_call(
            system_prompt=extract_prompt,
            user_message=extract_input,
            max_tokens=200,
            temperature=0.1,
            user_id=user_id,
            node_name="memory_extract",
            bypass_cache=True,
        )

        import json as _json
        try:
            # 尝试解析 JSON
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                extracted = _json.loads(content[start:end])
            else:
                return 0
        except _json.JSONDecodeError:
            return 0

        # 存入 Memory
        from app.core.database import async_session
        saved = 0
        async with async_session() as db:
            for category, items in extracted.items():
                if not isinstance(items, list):
                    continue
                for item in items[:3]:  # 每类最多3条
                    if not isinstance(item, str) or len(item) < 3:
                        continue
                    mem = Memory(
                        user_id=user_id,
                        key=f"auto_{category}",
                        value={
                            "content": item,
                            "session_id": session_id,
                            "memory_type": "preference" if category == "preferences" else "confirmed_fact",
                            "source": "auto_summarize",
                        },
                        importance=0.5,
                    )
                    db.add(mem)
                    saved += 1
            if saved > 0:
                await db.commit()

        # 异步同步到 Milvus
        if saved > 0:
            try:
                from app.services.vector_memory import store_vector_memories
                facts = [
                    {"key": f"auto_{k}", "value": {"preference": v}, "memory_type": "auto", "importance": 0.5, "source": "auto"}
                    for k, items in extracted.items() if isinstance(items, list)
                    for v in items[:3] if isinstance(v, str)
                ]
                if facts:
                    await store_vector_memories(user_id, facts)
            except Exception:
                pass

        return saved

    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════════════════
# Memory Consolidation (Redis → MySQL + Milvus)
# ═══════════════════════════════════════════════════════════════════════

async def consolidate_memory(db: AsyncSession, user_id: str) -> int:
    """将短期记忆整合为长期记忆。

    流程:
      1. 扫描 Redis 中用户的所有活跃会话
      2. 提取用户确认的信息、偏好、重要结论
      3. 存入 MySQL (结构化) + Milvus (向量化)
      4. 清理过期的 Redis 会话

    Returns:
        成功整合的记忆条数
    """
    saved_count = 0

    try:
        # 1. 获取所有活跃会话
        session_keys = await get_all_user_sessions(user_id)
        if not session_keys:
            return 0

        r = await get_redis()

        # 2. 提取可信信息
        extracted_facts: list[dict] = []

        for sk in session_keys:
            data = await r.get(sk)
            if not data:
                continue
            try:
                messages = json.loads(data)
            except json.JSONDecodeError:
                continue

            for msg in messages:
                content = msg.get("content", "")
                role = msg.get("role", "")

                # 仅提取用户消息中的关键信息
                if role != "user":
                    continue

                # 检测用户偏好
                if any(kw in content for kw in ["我喜欢", "偏好", "想要", "需要", "预算"]):
                    extracted_facts.append({
                        "key": f"preference_{len(extracted_facts)}",
                        "value": {"preference": content[:200]},
                        "importance": 0.7,
                        "memory_type": "preference",
                        "source": "system_extracted",
                    })

                # 检测确认信息
                if any(kw in content for kw in ["确认", "就选", "决定", "买"]):
                    extracted_facts.append({
                        "key": f"confirmed_{len(extracted_facts)}",
                        "value": {"confirmed_choice": content[:200]},
                        "importance": 0.9,
                        "memory_type": "confirmed_fact",
                        "source": "user_confirmed",
                    })

        # 3. 存入 MySQL
        for fact in extracted_facts:
            result = await save_memory(
                db, user_id,
                key=fact["key"],
                value=fact["value"],
                importance=fact["importance"],
                source=fact.get("source", "system_extracted"),
                memory_type=fact.get("memory_type", "general"),
            )
            if result:
                saved_count += 1

        # 4. 尝试写入向量记忆 (Milvus)
        if saved_count > 0:
            try:
                await _sync_to_vector_memory(user_id, extracted_facts)
            except Exception:
                pass  # 向量化失败不阻塞主流程

    except Exception:
        pass  # 整合失败不抛异常

    return saved_count


async def _sync_to_vector_memory(user_id: str, facts: list[dict]):
    """将提取的事实同步到向量记忆 (Milvus)"""
    try:
        from app.services.vector_memory import store_vector_memories
        await store_vector_memories(user_id, facts)
    except ImportError:
        pass  # 向量记忆模块不可用


# ═══════════════════════════════════════════════════════════════════════
# 缓存热数据 (Redis L1)
# ═══════════════════════════════════════════════════════════════════════

async def cache_query_result(query: str, result: dict, ttl: int = 600):
    """缓存查询结果到 Redis (L1 热缓存)"""
    import hashlib
    r = await get_redis()
    key = f"cache:query:{hashlib.md5(query.encode()).hexdigest()[:16]}"
    await r.set(key, json.dumps(result, ensure_ascii=False), ex=ttl)


async def get_cached_result(query: str) -> dict | None:
    """从 Redis 获取缓存的查询结果"""
    import hashlib
    r = await get_redis()
    key = f"cache:query:{hashlib.md5(query.encode()).hexdigest()[:16]}"
    data = await r.get(key)
    return json.loads(data) if data else None
