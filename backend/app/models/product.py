import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[float | None] = mapped_column(Float)
    original_price: Mapped[float | None] = mapped_column(Float)
    url: Mapped[str | None] = mapped_column(String(2048))
    image_url: Mapped[str | None] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(Text)
    specs: Mapped[dict | None] = mapped_column(JSON)
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column()
    source: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
