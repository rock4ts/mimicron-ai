from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import RateLimited, TokenUserDependency, UserServiceDependency
from app.schemas.user import (
    LoginDataOut,
    UserChangeEmailIn,
    UserChangePasswordIn,
    UserCreateIn,
    UserCreateOut,
    UserReadOut,
)

router = APIRouter(prefix="/users", tags=["user"])


@router.post("")
async def create_user(
    user_data: UserCreateIn,
    _rate_limited: RateLimited,
    user_service: UserServiceDependency,
) -> UserCreateOut:
    user = await user_service.create_user(user_data=user_data)
    return UserCreateOut.model_validate(user, from_attributes=True)


@router.get("/me")
async def user_info(
    user: TokenUserDependency,
    user_service: UserServiceDependency,
) -> UserReadOut:
    user = await user_service.get_user_info(user_id=user.id)
    return UserReadOut.model_validate(user, from_attributes=True)


@router.patch("/me/email")
async def change_email(
    change_email_data: UserChangeEmailIn,
    user: TokenUserDependency,
    user_service: UserServiceDependency,
) -> Response:
    await user_service.change_email(change_email_data=change_email_data, user=user)
    return Response(status_code=status.HTTP_200_OK)


@router.patch("/me/password")
async def change_password(
    change_password_data: UserChangePasswordIn,
    user: TokenUserDependency,
    user_service: UserServiceDependency,
) -> Response:
    await user_service.change_password(change_password_data=change_password_data, user=user)
    return Response(status_code=status.HTTP_200_OK)


@router.get("/me/login-history")
async def get_login_history(
    user: TokenUserDependency,
    user_service: UserServiceDependency,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 10,
) -> list[LoginDataOut]:
    return await user_service.get_login_history(user_id=user.id, page=page, page_size=page_size)
