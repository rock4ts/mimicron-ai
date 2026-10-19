import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.errors import (
    EmailAlreadyExistsError,
    UserAlreadyExistsError,
    UserNotFoundError,
    WrongPasswordError,
)
from app.models.user import User
from app.repositories.login_history_repository import LoginHistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    LoginDataOut,
    UserChangeEmailIn,
    UserChangePasswordIn,
    UserCreateIn,
)
from app.security import hash_password, verify_password

logger = logging.getLogger(__name__)


class UserService:
    def __init__(
        self,
        user_repository: UserRepository,
        login_history_repository: LoginHistoryRepository,
    ) -> None:
        self.user_repository = user_repository
        self.login_history_repository = login_history_repository

    async def create_user(self, user_data: UserCreateIn) -> User:
        existing_user = await self.user_repository.get_by_email(user_data.email)
        if existing_user:
            raise UserAlreadyExistsError()

        user = User(
            email=user_data.email,
            password_hash=hash_password(user_data.password),
        )
        try:
            user = await self.user_repository.add(user)
            await self.user_repository.uow.commit()
        except IntegrityError:
            logger.info("User already exists (integrity)")
            await self.user_repository.uow.session.rollback()
            raise UserAlreadyExistsError() from None
        await self.user_repository.uow.refresh(user)
        return user

    async def change_email(self, change_email_data: UserChangeEmailIn, user: User) -> None:
        if not verify_password(change_email_data.password, user.password_hash):
            raise WrongPasswordError()
        user.email = change_email_data.email
        try:
            await self.user_repository.uow.commit()
        except IntegrityError:
            logger.info("Email already exists (integrity)")
            await self.user_repository.uow.session.rollback()
            raise EmailAlreadyExistsError() from None

    async def change_password(
        self,
        change_password_data: UserChangePasswordIn,
        user: User,
    ) -> None:
        if not verify_password(change_password_data.old_password, user.password_hash):
            raise WrongPasswordError("Wrong current password")
        user.password_hash = hash_password(change_password_data.new_password)
        user.token_version += 1
        await self.user_repository.uow.commit()

    async def get_login_history(
        self, user_id: UUID, page: int, page_size: int
    ) -> list[LoginDataOut]:
        records = await self.login_history_repository.list_for_user(user_id, page, page_size)
        return [LoginDataOut.model_validate(record, from_attributes=True) for record in records]

    async def get_user_info(self, user_id: UUID) -> User:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        return user
