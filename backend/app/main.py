from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.core.database import engine, Base, async_session
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.price_history import PriceHistory
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.products import router as products_router
from app.api.v1.reports import router as reports_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.profile import router as profile_router, public_model_router
from app.api.v1.admin import router as admin_router
from app.api.v1.memory import router as memory_router
from app.api.v1.admin import append_log
from mcp_server.routes import router as mcp_router

settings = get_settings()


async def seed_default_users():
    from sqlalchemy import select, update
    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == "admin@eva.com"))
        if result.scalar_one_or_none() is None:
            admin = User(
                email="admin@eva.com",
                name="EVA Admin",
                password_hash=hash_password("admin123"),
                role=UserRole.admin,
                remaining_questions=-1,  # -1 表示无限额
            )
            db.add(admin)
        else:
            # 确保已有管理员拥有无限额
            await db.execute(
                update(User)
                .where(User.email == "admin@eva.com", User.role == UserRole.admin)
                .values(remaining_questions=-1)
            )
        result = await db.execute(select(User).where(User.email == "user@eva.com"))
        if result.scalar_one_or_none() is None:
            user = User(
                email="user@eva.com",
                name="Demo User",
                password_hash=hash_password("user123"),
                role=UserRole.user,
                remaining_questions=20,
            )
            db.add(user)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 迁移：为旧数据库添加新字段
        await _migrate_user_quota_fields(conn)
    await seed_default_users()
    yield


async def _migrate_user_quota_fields(conn):
    """为旧版本数据库添加 remaining_questions 和 total_questions_used 字段。"""
    import re
    db_url = settings.async_database_url
    is_sqlite = "sqlite" in db_url
    try:
        if is_sqlite:
            # SQLite: 使用 ALTER TABLE 添加列（仅当列不存在时）
            from sqlalchemy import text
            # 检查列是否存在
            for col_name, col_default in [("remaining_questions", "20"), ("total_questions_used", "0")]:
                try:
                    await conn.execute(text(
                        f"ALTER TABLE users ADD COLUMN {col_name} INTEGER NOT NULL DEFAULT {col_default}"
                    ))
                except Exception:
                    # 列已存在，跳过
                    pass
        else:
            # MySQL: 类似的迁移逻辑
            from sqlalchemy import text
            for col_name, col_default in [("remaining_questions", "20"), ("total_questions_used", "0")]:
                try:
                    await conn.execute(text(
                        f"ALTER TABLE users ADD COLUMN {col_name} INTEGER NOT NULL DEFAULT {col_default}"
                    ))
                except Exception:
                    pass
    except Exception:
        # 迁移失败不阻止启动
        pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(favorites_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(public_model_router, prefix="/api/v1")

# MCP Server — SSE transport (STDIO transport via mcp_server/server.py)
app.include_router(mcp_router, prefix="/mcp")


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
