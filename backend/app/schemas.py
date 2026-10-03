from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Envelope(BaseModel):
    code: int | str
    message: str
    data: object | None = None


class RegisterRequest(BaseModel):
    username: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    status: str
    created_at: datetime
