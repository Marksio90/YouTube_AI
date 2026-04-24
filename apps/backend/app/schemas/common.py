from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class MessageResponse(BaseModel):
    message: str


class TaskResponse(BaseModel):
    task_id: str
    status: str
