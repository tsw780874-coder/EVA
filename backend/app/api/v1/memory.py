"""Agent Memory API — 长期记忆 CRUD + 语义搜索"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db, require_user
from app.models.user import User
from app.models.memory import Memory

router = APIRouter(prefix="/memory", tags=["memory"])


class SaveMemoryRequest(BaseModel):
    key: str = Field(description="记忆标识")
    value: dict = Field(description="记忆内容 (JSON)")
    importance: float = Field(default=0.5, ge=0, le=1.0)
    ttl: int | None = Field(default=None, description="过期时间（秒）")


class MemoryResponse(BaseModel):
    id: str
    key: str
    value: dict
    importance: float
    created_at: str


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == current_user.id)
        .order_by(Memory.updated_at.desc())
        .limit(limit)
    )
    memories = result.scalars().all()
    return [
        MemoryResponse(
            id=m.id, key=m.key, value=m.value or {},
            importance=m.importance or 0.5,
            created_at=m.created_at.isoformat(),
        )
        for m in memories
    ]


@router.post("", status_code=201)
async def save_memory(
    body: SaveMemoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """保存一条记忆（存在即更新）"""
    # 检查是否已有同名 key
    existing = await db.execute(
        select(Memory).where(
            Memory.user_id == current_user.id,
            Memory.key == body.key,
        )
    )
    existing_memory = existing.scalar_one_or_none()

    if existing_memory:
        existing_memory.value = body.value
        existing_memory.importance = body.importance
        existing_memory.updated_at = datetime.now(timezone.utc)
        db.add(existing_memory)
        await db.commit()
        return {"id": existing_memory.id, "message": "记忆已更新"}

    memory = Memory(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        key=body.key,
        value=body.value,
        importance=body.importance,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(memory)
    await db.commit()
    return {"id": memory.id, "message": "记忆已保存"}


@router.get("/search")
async def search_memories(
    q: str = Query(description="搜索关键词"),
    limit: int = Query(default=10, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """搜索记忆（基于 key 模糊匹配）"""
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == current_user.id,
            Memory.key.contains(q),
        )
        .order_by(Memory.importance.desc())
        .limit(limit)
    )
    memories = result.scalars().all()
    return [
        {
            "id": m.id, "key": m.key, "value": m.value,
            "importance": m.importance, "created_at": m.created_at.isoformat(),
        }
        for m in memories
    ]


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    result = await db.execute(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == current_user.id,
        )
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    await db.delete(memory)
    await db.commit()
    return {"message": "记忆已删除"}
