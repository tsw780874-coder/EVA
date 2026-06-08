from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.models.user import User
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token


async def register_user(db: AsyncSession, email: str, name: str, password: str) -> tuple[User, str, str]:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册")

    user = User(email=email, name=name, password_hash=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return user, access_token, refresh_token


async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return user, access_token, refresh_token


async def refresh_token(db: AsyncSession, token: str) -> tuple[User, str, str]:
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的刷新令牌")
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的刷新令牌")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的刷新令牌")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)
    return user, access_token, new_refresh_token
