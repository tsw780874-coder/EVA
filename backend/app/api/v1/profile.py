from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from app.api.deps import get_db, require_user
from app.models.user import User
from app.models.favorite import Favorite
from app.models.product import Product
from app.models.report import Report
from app.core.security import hash_password, verify_password
from app.core.llm import get_models_for_role, get_available_models

router = APIRouter(prefix="/profile", tags=["profile"])


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    avatar_url: str | None = None
    preferred_model: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


@router.get("")
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    # 统计数据
    favorites_count = (await db.execute(
        select(func.count(Favorite.id)).where(Favorite.user_id == current_user.id)
    )).scalar() or 0
    reports_count = (await db.execute(
        select(func.count(Report.id)).where(Report.user_id == current_user.id)
    )).scalar() or 0

    # 计算节省金额（收藏商品的原价-现价总和）
    savings_result = await db.execute(
        select(func.sum(Product.original_price - Product.price))
        .select_from(Favorite)
        .join(Product, Favorite.product_id == Product.id)
        .where(Favorite.user_id == current_user.id)
        .where(Product.original_price > Product.price)
    )
    total_savings = savings_result.scalar() or 0

    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role.value,
        "avatar_url": current_user.avatar_url,
        "preferred_model": getattr(current_user, "preferred_model", None),
        "created_at": current_user.created_at.isoformat(),
        "total_savings": round(float(total_savings), 2),
        "favorites_count": favorites_count,
        "reports_count": reports_count,
        "purchase_count": favorites_count,
    }


@router.put("")
async def update_profile(
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    if body.name is not None:
        current_user.name = body.name
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    if body.preferred_model is not None:
        current_user.preferred_model = body.preferred_model

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role.value,
        "avatar_url": current_user.avatar_url,
        "preferred_model": getattr(current_user, "preferred_model", None),
    }


@router.put("/password")
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")

    current_user.password_hash = hash_password(body.new_password)
    db.add(current_user)
    await db.commit()

    return {"message": "密码已更新"}


# 公开模型列表（所有已认证用户可访问）
public_model_router = APIRouter(prefix="/models", tags=["models"])


@public_model_router.get("")
async def get_public_models(
    current_user: User = Depends(require_user),
):
    """返回当前用户角色可用的模型列表"""
    return {"models": get_models_for_role(current_user.role.value)}
