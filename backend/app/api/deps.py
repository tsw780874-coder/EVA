from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import async_session
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except Exception:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def require_user(
    current_user: User | None = Depends(get_current_user),
) -> User:
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return current_user


async def require_admin(
    current_user: User = Depends(require_user),
) -> User:
    if current_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


async def check_quota(
    current_user: User = Depends(require_user),
) -> User:
    """检查用户使用额度。管理员无限额，普通用户检查剩余问题数。"""
    if current_user.role.value == "admin":
        return current_user
    if current_user.remaining_questions <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="您的提问额度已用完，请联系管理员获取更多额度",
        )
    return current_user


async def check_rate_limit(
    current_user: User = Depends(require_user),
) -> User:
    """滑动窗口速率限制。管理员无限速。"""
    if current_user.role.value == "admin":
        return current_user
    from app.core.rate_limiter import default_limiter
    await default_limiter.check(current_user.id)
    return current_user
