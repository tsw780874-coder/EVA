from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.api.deps import get_db, require_user
from app.models.user import User
from app.models.favorite import Favorite
from app.models.product import Product
from app.api.v1.admin import append_log

router = APIRouter(prefix="/favorites", tags=["favorites"])


class AddFavoriteRequest(BaseModel):
    product_id: str
    product_name: str = ""
    product_platform: str = ""
    product_price: float = 0
    product_url: str = ""
    product_image_url: str = ""
    notes: str | None = None


@router.get("")
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    result = await db.execute(
        select(Favorite)
        .options(selectinload(Favorite.product))
        .where(Favorite.user_id == current_user.id)
        .order_by(Favorite.created_at.desc())
    )
    favs = result.scalars().all()
    return [
        {
            "id": f.id,
            "product": {
                "id": f.product.id, "name": f.product.name,
                "platform": f.product.platform, "price": f.product.price,
                "image_url": f.product.image_url,
            } if f.product else None,
            "notes": f.notes,
            "created_at": f.created_at.isoformat(),
        }
        for f in favs
    ]


@router.post("", status_code=201)
async def add_favorite(
    body: AddFavoriteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    # 检查商品是否存在，不存在则自动创建
    result = await db.execute(select(Product).where(Product.id == body.product_id))
    product = result.scalar_one_or_none()

    if not product and body.product_name:
        product = Product(
            id=body.product_id,
            name=body.product_name,
            platform=body.product_platform,
            price=body.product_price if body.product_price > 0 else None,
            url=body.product_url or None,
            image_url=body.product_image_url or None,
        )
        db.add(product)
        await db.flush()
        append_log("INFO", f"自动创建商品: {body.product_name} ({body.product_platform})")

    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 检查是否已收藏
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == current_user.id,
            Favorite.product_id == body.product_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="已收藏过该商品")

    fav = Favorite(user_id=current_user.id, product_id=body.product_id, notes=body.notes)
    db.add(fav)
    await db.commit()
    await db.refresh(fav)
    return {"id": fav.id, "status": "added"}


@router.delete("/{favorite_id}")
async def remove_favorite(
    favorite_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    result = await db.execute(
        select(Favorite).where(Favorite.id == favorite_id, Favorite.user_id == current_user.id)
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="收藏不存在")
    await db.delete(fav)
    await db.commit()
    return {"status": "removed"}
