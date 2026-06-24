import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.core.database import engine, Base, async_session
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.products import router as products_router
from app.api.v1.reports import router as reports_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.profile import router as profile_router, public_model_router
from app.api.v1.admin import router as admin_router
from app.api.v1.memory import router as memory_router
from app.api.v1.admin import append_log

settings = get_settings()


async def seed_default_users():
    from sqlalchemy import select
    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == "admin@eva.com"))
        if result.scalar_one_or_none() is None:
            admin = User(
                email="admin@eva.com",
                name="EVA Admin",
                password_hash=hash_password("admin123"),
                role=UserRole.admin,
            )
            db.add(admin)
        result = await db.execute(select(User).where(User.email == "user@eva.com"))
        if result.scalar_one_or_none() is None:
            user = User(
                email="user@eva.com",
                name="Demo User",
                password_hash=hash_password("user123"),
                role=UserRole.user,
            )
            db.add(user)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_default_users()

    # ── Milvus warmup + auto-seed (non-blocking, best-effort) ──
    asyncio.create_task(_warmup_and_seed())

    yield


async def _warmup_and_seed():
    """Warm up Milvus connection and seed knowledge base if empty.

    Fire-and-forget — failures do not block server startup.
    """
    try:
        from app.agent.pipeline import warmup_milvus
        await warmup_milvus()
    except Exception:
        pass

    try:
        from app.services.milvus_seed import auto_seed_on_startup
        await auto_seed_on_startup()
    except Exception:
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


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
