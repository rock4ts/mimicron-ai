from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from typing import Any, ClassVar
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
import pydantic
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.errors import (
    YandexIdAccountConflictError,
    YandexIdProviderError,
    YandexIdStateError,
    YandexIdTokenError,
    YandexIdUserInfoError,
)
from app.models.oauth_account import YANDEX_PROVIDER, OAuthAccount
from app.models.user import User
from app.repositories.login_history_repository import LoginHistoryRepository
from app.repositories.oauth_account_repository import OAuthAccountRepository
from app.repositories.user_repository import UserRepository
from app.schemas.misc import DeviceInfo, RequestMeta
from app.schemas.yandexid import (
    YandexIdAuthorizeParams,
    YandexIdCodeVerifier,
    YandexIdTokenData,
    YandexIdTokenRequestData,
    YandexIdUserData,
    YandexIdUserRequestParams,
)
from app.security import hash_password, issue_token_pair

logger = logging.getLogger(__name__)


class YandexIdService:
    _STATE_CACHE_PREFIX: ClassVar[str] = f"oauth:{YANDEX_PROVIDER}:state"
    _PKCE_METHOD: ClassVar[str] = "S256"
    _PKCE_VERIFIER_NBYTES: ClassVar[int] = 64

    def __init__(
        self,
        user_repository: UserRepository,
        oauth_account_repository: OAuthAccountRepository,
        login_history_repository: LoginHistoryRepository,
        redis: Redis,
        settings: Settings,
    ) -> None:
        self.user_repository = user_repository
        self.oauth_account_repository = oauth_account_repository
        self.login_history_repository = login_history_repository
        self.redis = redis
        self.settings = settings

    def _state_cache_key(self, state: UUID | str) -> str:
        return f"{self._STATE_CACHE_PREFIX}:{state}"

    async def build_login_redirect(self, state: UUID) -> str:
        yandexid = self.settings.yandexid
        code_verifier = self._generate_code_verifier()
        login_params = self._build_login_params(state, code_verifier)
        try:
            await self.redis.setex(
                self._state_cache_key(login_params.state),
                yandexid.confirmation_code_ttl,
                json.dumps({"code_verifier": code_verifier}),
            )
        except RedisError as exc:
            logger.info("Failed to initialize Yandex authorization state")
            raise YandexIdProviderError("Failed to initialize Yandex authorization state") from exc

        query = urlencode(login_params.model_dump(mode="json", exclude_none=True))
        return f"{yandexid.auth_url}?{query}"

    async def authorize(
        self,
        code: str,
        state: UUID,
        request_meta: RequestMeta,
        device_info: DeviceInfo,
    ):
        cached_state = await self._consume_cached_state(state=state)
        token_data = await self._exchange_code(
            code=code,
            code_verifier=cached_state.code_verifier,
            device_info=device_info,
        )
        user_data = await self._fetch_user_info(access_token=token_data.access_token)
        user = await self._resolve_user(user_data)
        tokens = issue_token_pair(user, self.settings.jwt)
        try:
            await self.login_history_repository.add(
                user_id=user.id,
                request_meta=request_meta,
                device_info=device_info,
            )
            await self.login_history_repository.uow.commit()
        except Exception:
            logger.info("Failed to persist Yandex login history", exc_info=True)
            await self.login_history_repository.uow.session.rollback()
        return tokens

    def _build_login_params(self, state: UUID, code_verifier: str) -> YandexIdAuthorizeParams:
        yandexid = self.settings.yandexid
        return YandexIdAuthorizeParams.model_validate(
            {
                "client_id": yandexid.client_id,
                "state": state,
                "redirect_uri": yandexid.redirect_url,
                "code_verifier": code_verifier,
                "code_challenge": self._generate_code_challenge(code_verifier),
                "code_challenge_method": self._PKCE_METHOD,
            }
        )

    async def _consume_cached_state(self, state: UUID) -> YandexIdCodeVerifier:
        try:
            payload = await self.redis.getdel(self._state_cache_key(state))
        except RedisError as exc:
            logger.info("Failed to validate Yandex authorization state")
            raise YandexIdProviderError("Failed to validate Yandex authorization state") from exc
        if payload is None:
            raise YandexIdStateError()
        try:
            return YandexIdCodeVerifier.model_validate_json(payload)
        except pydantic.ValidationError as exc:
            logger.info("Yandex authorization state payload is invalid")
            raise YandexIdStateError() from exc

    async def _exchange_code(
        self,
        code: str,
        code_verifier: str,
        device_info: DeviceInfo | None = None,
    ) -> YandexIdTokenData:
        yandexid = self.settings.yandexid
        payload = YandexIdTokenRequestData(
            code=code,
            code_verifier=code_verifier,
            device_id=device_info.device_id if device_info else None,
            device_name=device_info.device_name if device_info else None,
        )
        try:
            async with httpx.AsyncClient(timeout=yandexid.http_timeout_seconds) as client:
                response = await client.post(
                    yandexid.token_url,
                    data=payload.model_dump(exclude_none=True),
                    headers={"Authorization": yandexid.auth_header},
                )
        except httpx.RequestError as exc:
            logger.info("Failed to request Yandex token")
            raise YandexIdTokenError("Error during Yandex token exchange request") from exc

        response_data = self._safe_json(response)
        if response.is_error:
            logger.warning(
                "Yandex token exchange failed status=%s error=%s",
                response.status_code,
                response_data.get("error"),
            )
            raise YandexIdTokenError("Yandex token exchange failed")
        try:
            return YandexIdTokenData.model_validate(response_data)
        except pydantic.ValidationError as exc:
            logger.info("Yandex token response payload is invalid")
            raise YandexIdProviderError("Yandex token response payload is invalid") from exc

    async def _fetch_user_info(self, access_token: str) -> YandexIdUserData:
        yandexid = self.settings.yandexid
        params = YandexIdUserRequestParams().model_dump(exclude_none=True)
        try:
            async with httpx.AsyncClient(timeout=yandexid.http_timeout_seconds) as client:
                response = await client.get(
                    yandexid.user_info_url,
                    params=params,
                    headers={"Authorization": f"OAuth {access_token}"},
                )
        except httpx.RequestError as exc:
            logger.info("Failed to request Yandex user info")
            raise YandexIdUserInfoError("Error during Yandex user info request") from exc

        response_data = self._safe_json(response)
        if response.is_error:
            logger.warning(
                "Yandex user info failed status=%s error=%s",
                response.status_code,
                response_data.get("error"),
            )
            raise YandexIdUserInfoError("Yandex user info request returned an error")
        try:
            return YandexIdUserData.model_validate(response_data)
        except pydantic.ValidationError as exc:
            logger.info("Yandex user info response payload is invalid")
            raise YandexIdUserInfoError("Yandex user info response payload is invalid") from exc

    async def _resolve_user(self, yandex_user_data: YandexIdUserData) -> User:
        provider_user_id = str(yandex_user_data.id)
        linked_user = await self.oauth_account_repository.get_user_by_provider_account(
            YANDEX_PROVIDER,
            provider_user_id,
        )
        if linked_user:
            return linked_user

        existing_user = await self.user_repository.get_by_email(yandex_user_data.default_email)
        if existing_user:
            return await self._attach_oauth_account(
                user=existing_user,
                provider_user_id=provider_user_id,
            )

        new_user = User(
            email=yandex_user_data.default_email,
            first_name=yandex_user_data.first_name,
            last_name=yandex_user_data.last_name,
            password_hash=hash_password(str(uuid4())),
        )
        await self.user_repository.add(new_user)
        return await self._attach_oauth_account(user=new_user, provider_user_id=provider_user_id)

    async def _attach_oauth_account(self, user: User, provider_user_id: str) -> User:
        await self.oauth_account_repository.add(
            OAuthAccount(
                user_id=user.id,
                provider=YANDEX_PROVIDER,
                provider_user_id=provider_user_id,
            )
        )
        try:
            await self.user_repository.uow.commit()
        except IntegrityError as exc:
            logger.info("Yandex account link conflict (integrity)")
            await self.user_repository.uow.session.rollback()
            raise YandexIdAccountConflictError() from exc
        await self.user_repository.uow.refresh(user)
        return user

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            logger.info("Failed to parse Yandex response as JSON")
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _generate_code_verifier(cls) -> str:
        return secrets.token_urlsafe(cls._PKCE_VERIFIER_NBYTES)

    @staticmethod
    def _generate_code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")
