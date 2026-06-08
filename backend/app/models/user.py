import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    guest = "guest"
    user = "user"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.user, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    preferred_model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sessions = relationship("ChatSession", back_populates="user")
    reports = relationship("Report", back_populates="user")
    favorites = relationship("Favorite", back_populates="user")
    agent_runs = relationship("AgentRun", back_populates="user")
    memories = relationship("Memory", back_populates="user")
