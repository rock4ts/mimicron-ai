from typing import Literal

from pydantic import UUID4, BaseModel


class AccessTokenPayload(BaseModel):
    sub: UUID4
    iat: int
    exp: int
    jti: UUID4
    tv: int
    type: Literal["access"]
    is_superuser: bool
