from typing import Literal

from pydantic import UUID4, BaseModel, EmailStr


class UserLoginData(BaseModel):
    email: EmailStr
    password: str


class AccessTokenResponse(BaseModel):
    access: str


class TokenData(BaseModel):
    access: str
    refresh: str


class BaseTokenPayload(BaseModel):
    sub: UUID4
    iat: int
    exp: int
    jti: UUID4
    tv: int


class AccessTokenPayload(BaseTokenPayload):
    type: Literal["access"]
    is_superuser: bool


class RefreshTokenPayload(BaseTokenPayload):
    type: Literal["refresh"]
