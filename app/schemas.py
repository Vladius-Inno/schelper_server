from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: str


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6)


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    token: str
    refresh_token: Optional[str] = None


class RegisterResponse(UserOut):
    token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LinkRequest(BaseModel):
    parent_id: int
    child_id: int
    relation_type: Optional[str] = None


class StatusResponse(BaseModel):
    status: str


# Tasks domain

class SubtaskBase(BaseModel):
    title: str
    type: str | None = None


class SubtaskCreate(SubtaskBase):
    pass


class SubtaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = None  # todo | in_progress | done | checked
    parent_reaction: str | None = None  # e.g., thumbs-up, star, party reaction


class SubtaskOut(BaseModel):
    id: int
    title: str
    status: str
    type: str | None = None
    parent_reaction: str | None = None  # e.g., thumbs-up, star, party reaction
    position: int | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = None


class TaskCreate(BaseModel):
    subject_id: int
    date: str | None = None  # YYYY-MM-DD; default is today
    title: str | None = None
    hash: str | None = None
    subtasks: list[SubtaskCreate] | None = None
    child_id: int | None = None


class TaskOut(BaseModel):
    id: int
    child_id: int
    subject_id: int
    date: str
    title: str | None
    hash: str
    status: str
    subtasks: list[SubtaskOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Subjects domain

class SubjectCreate(BaseModel):
    name: str


class SubjectOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class SubjectUpdate(BaseModel):
    name: str


class HomeworkImportRequest(BaseModel):
    child_id: Optional[int] = None
    text: Optional[str] = None
    file_id: Optional[str] = None  # если загружаем картинку/пдф


class TaskResponse(BaseModel):
    status: Literal["created", "updated", "duplicate"]
    task: TaskOut
