import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    input_data: Mapped[dict | None] = mapped_column("input", JSON)
    output_data: Mapped[dict | None] = mapped_column("output", JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="agent_runs")
