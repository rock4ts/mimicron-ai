from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.config import JWTSettings
from app.models.user import User
from app.schemas.auth import AccessTokenPayload, RefreshTokenPayload, TokenData

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def create_access_token(user: User, jwt_settings: JWTSettings) -> str:
    now = datetime.now(UTC)
    payload = AccessTokenPayload(
        type="access",
        sub=user.id,
        iat=int(now.timestamp()),
        exp=int((now + timedelta(minutes=jwt_settings.access_token_expire_minutes)).timestamp()),
        jti=uuid4(),
        tv=user.token_version,
        is_superuser=user.is_superuser,
    ).model_dump(mode="json")
    return jwt.encode(payload, jwt_settings.private_key, algorithm=jwt_settings.algorithm)


def create_refresh_token(user: User, jwt_settings: JWTSettings) -> str:
    now = datetime.now(UTC)
    payload = RefreshTokenPayload(
        type="refresh",
        sub=user.id,
        iat=int(now.timestamp()),
        exp=int((now + timedelta(days=jwt_settings.refresh_token_expire_days)).timestamp()),
        jti=uuid4(),
        tv=user.token_version,
    ).model_dump(mode="json")
    return jwt.encode(payload, jwt_settings.private_key, algorithm=jwt_settings.algorithm)


def issue_token_pair(user: User, jwt_settings: JWTSettings) -> TokenData:
    return TokenData(
        access=create_access_token(user, jwt_settings),
        refresh=create_refresh_token(user, jwt_settings),
    )
