"""Auth request schemas (structure only).

Password rules are NOT validated here: they come from the organization's
security policy (services/security_policy.py), the single source of truth.
"""
import re

from pydantic import BaseModel, Field, validator


class UserRegister(BaseModel):
    email: str
    password: str = Field(..., min_length=1, max_length=1024)
    name: str = Field(..., min_length=1, max_length=255)

    @validator('email')
    def validate_email(cls, v):
        # Allow .local domains for development
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v) and not v.endswith('.local'):
            raise ValueError('Invalid email address')
        return v


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: dict


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=1, max_length=1024)
