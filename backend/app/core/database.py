from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

_db_url = settings.async_database_url
_is_sqlite = "sqlite" in _db_url
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_async_engine(
    _db_url,
    echo=settings.debug,
    pool_size=5 if _is_sqlite else 20,
    max_overflow=5 if _is_sqlite else 10,
    pool_pre_ping=True,
    pool_recycle=1800 if not _is_sqlite else -1,
    connect_args=_connect_args,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
