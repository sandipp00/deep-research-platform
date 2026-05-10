import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    token: str
    id: uuid.UUID
    email: str
    name: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class RenameConversationRequest(BaseModel):
    title: str | None = None


class ConversationDto(CamelModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageDto(CamelModel):
    id: uuid.UUID
    role: str
    content: str | None
    blocks: list[Any] | None
    sources: list[str] | None
    follow_ups: list[Any] | None
    created_at: datetime


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
