import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import Role


def _strong(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if len(v) < 10 or not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
        raise ValueError("Password must be at least 10 characters and contain letters and digits")
    return v


class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: str  # responses: stored value, not re-validated (special-use domains like .local exist in demo data)


class UserCreate(UserBase):
    email: EmailStr
    password: str = Field(..., max_length=72)
    role: Role
    title: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=50)
    facility_ids: List[uuid.UUID] = []
    region_ids: List[uuid.UUID] = []

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        return _strong(v)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    title: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = Field(None, max_length=72)

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        return _strong(v)


class AssignmentIn(BaseModel):
    facility_ids: List[uuid.UUID] = []
    region_ids: List[uuid.UUID] = []


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    facility_id: Optional[uuid.UUID]
    region_id: Optional[uuid.UUID]
    facility_name: Optional[str] = None
    region_name: Optional[str] = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: Role
    is_active: bool
    title: Optional[str] = None
    phone: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    locked_until: Optional[datetime] = None


class UserDetail(UserResponse):
    assignments: List[AssignmentOut] = []


class MeResponse(UserResponse):
    permissions: List[str]
    role_label: str
    global_scope: bool
    facility_ids: List[uuid.UUID]
    region_ids: List[uuid.UUID]
