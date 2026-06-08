import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, JSON, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value: Mapped[dict | None] = mapped_column(JSON)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    ttl: Mapped[int | None] = mapped_column(Integer)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="memories")
