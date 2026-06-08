"""
Agent Memory Service: short-term (Redis) + long-term (MySQL + Milvus).
"""
import json
from datetime import datetime, timezone
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.models.memory import Memory

settings = get_settings()


# ---- Short-term memory (Redis) ----

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def save_session_history(user_id: str, session_id: str, messages: list[dict], ttl: int = 86400):
    r = await get_redis()
    key = f"session:{user_id}:{session_id}"
    await r.set(key, json.dumps(messages, ensure_ascii=False), ex=ttl)


async def get_session_history(user_id: str, session_id: str) -> list[dict]:
    r = await get_redis()
    key = f"session:{user_id}:{session_id}"
    data = await r.get(key)
    return json.loads(data) if data else []


# ---- Long-term memory (MySQL) ----

async def save_memory(
    db: AsyncSession,
    user_id: str,
    key: str,
    value: dict,
    importance: float = 0.5,
    ttl: int | None = None,
) -> Memory:
    result = await db.execute(
        select(Memory).where(Memory.user_id == user_id, Memory.key == key)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = value
        existing.importance = importance
        existing.last_accessed = datetime.now(timezone.utc)
    else:
        existing = Memory(
            user_id=user_id, key=key, value=value,
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
) -> list[Memory]:
    q = select(Memory).where(Memory.user_id == user_id)
    if keyword:
        q = q.where(Memory.key.ilike(f"%{keyword}%"))
    q = q.order_by(Memory.importance.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def consolidate_memory(db: AsyncSession, user_id: str) -> int:
    """Consolidate short-term memories into long-term storage."""
    # Placeholder: in production, would summarize recent Redis sessions
    # and store important findings in MySQL + Milvus
    return 0
