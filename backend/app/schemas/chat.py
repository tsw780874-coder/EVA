from pydantic import BaseModel, Field
from datetime import datetime


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    metadata_: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = []

    model_config = {"from_attributes": True}


class ChatSessionListResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class CreateSessionRequest(BaseModel):
    title: str = "新对话"


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class SendMessageResponse(BaseModel):
    session_id: str
    user_message: ChatMessageResponse
    reply: str
