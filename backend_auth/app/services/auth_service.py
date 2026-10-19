import logging
from datetime import UTC, datetime

import jwt
import pydantic
from redis.asyncio import Redis

from app.config import JWTSettings
from app.errors import RefreshTokenError, UserNotFoundError, WrongCredentialsError
from app.models.user import User
from app.repositories.login_history_repository import LoginHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import RefreshTokenPayload, TokenData, UserLoginData
from app.schemas.misc import DeviceInfo, RequestMeta
from app.security import issue_token_pair, verify_password

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        login_history_repository: LoginHistoryRepository,
        redis: Redis,
        jwt_settings: JWTSettings,
    ) -> None:
        self.user_repository = user_repository
        self.login_history_repository = login_history_repository
        self.redis = redis
        self.jwt_settings = jwt_settings

    async def login_user(
        self,
        login_data: UserLoginData,
        request_meta: RequestMeta,
        device_info: DeviceInfo | None = None,
    ) -> TokenData:
        user = await self.user_repository.get_by_email(login_data.email)
        if not user or not verify_password(login_data.password, user.password_hash):
            raise WrongCredentialsError()

        tokens = issue_token_pair(user, self.jwt_settings)
        try:
            await self.login_history_repository.add(user.id, request_meta, device_info)
            await self.login_history_repository.uow.commit()
        except Exception:
            logger.info("Failed to persist login history", exc_info=True)
            await self.login_history_repository.uow.session.rollback()
        return tokens

    async def refresh_tokens(self, refresh_token: str) -> TokenData:
        payload = self._decode_refresh_token(refresh_token)
        if await self._is_blacklisted(str(payload.jti)):
            raise RefreshTokenError("Token is invalid")

        user = await self.user_repository.get_by_id(payload.sub)
        if not user:
            raise RefreshTokenError("User not found")
        if payload.tv != user.token_version:
            raise RefreshTokenError("Token version mismatch")

        await self._blacklist_token(
            str(payload.jti),
            max(1, payload.exp - int(datetime.now(UTC).timestamp())),
        )
        return issue_token_pair(user, self.jwt_settings)

    async def logout(self, refresh_token: str) -> None:
        payload = self._decode_refresh_token(refresh_token)
        ttl = payload.exp - int(datetime.now(UTC).timestamp())
        if ttl <= 0:
            return
        await self._blacklist_token(str(payload.jti), ttl)

    async def logout_others(self, user: User) -> TokenData:
        user.token_version += 1
        await self.user_repository.uow.commit()
        updated_user = await self.user_repository.get_by_id(user.id)
        if not updated_user:
            raise UserNotFoundError()
        return issue_token_pair(updated_user, self.jwt_settings)

    def _decode_refresh_token(self, refresh_token: str) -> RefreshTokenPayload:
        try:
            payload = jwt.decode(
                refresh_token,
                self.jwt_settings.public_key,
                algorithms=[self.jwt_settings.algorithm],
            )
        except jwt.ExpiredSignatureError:
            logger.info("Refresh token expired")
            raise RefreshTokenError("Token has expired") from None
        except jwt.InvalidTokenError:
            logger.info("Invalid refresh token")
            raise RefreshTokenError("Invalid token") from None

        try:
            validated = RefreshTokenPayload.model_validate(payload)
        except pydantic.ValidationError:
            logger.info("Invalid refresh token payload")
            raise RefreshTokenError("Invalid token payload") from None
        if validated.type != "refresh":
            raise RefreshTokenError("Token is not a refresh token")
        return validated

    async def _is_blacklisted(self, jti: str) -> bool:
        return await self.redis.get(f"blacklist:{jti}") is not None

    async def _blacklist_token(self, jti: str, ttl: int) -> None:
        await self.redis.setex(f"blacklist:{jti}", ttl, "true")
