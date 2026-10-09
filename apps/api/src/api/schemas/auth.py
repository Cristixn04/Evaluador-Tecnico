from pydantic import BaseModel, EmailStr, Field

from src.db.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AuthToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    organization_id: str
