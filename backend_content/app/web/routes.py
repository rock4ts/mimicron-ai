from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.api.dependencies import (
    ChatServiceDependency,
    CompanionServiceDependency,
    ConversationServiceDependency,
)
from app.errors import LLMProviderError
from app.schemas.companion import CompanionCreate, CompanionUpdate
from app.schemas.message import MessageCreate
from app.web.templates import templates

router = APIRouter(prefix="/ui", include_in_schema=False)


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def validation_errors(exc: ValidationError) -> dict[str, str]:
    errors: dict[str, str] = {}
    for error in exc.errors():
        field = str(error["loc"][-1])
        message = str(error["msg"]).removeprefix("Value error, ")
        _ = errors.setdefault(field, message)
    return errors


def template_response(
    request: Request,
    *,
    page: str,
    partial: str,
    context: dict[str, object],
    status_code: int = status.HTTP_200_OK,
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name=partial if is_htmx(request) else page,
        context=context,
        status_code=status_code,
    )


def html_error_if_app(
    *,
    title: str,
    message: str,
    status_code: int,
) -> Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]]:
    def decorator(
        handler: Callable[..., Awaitable[Response]],
    ) -> Callable[..., Awaitable[Response]]:
        @wraps(handler)
        async def wrapper(request: Request, exc: RequestValidationError) -> Response:
            if request.url.path.startswith("/ui"):
                return template_response(
                    request,
                    page="errors/page.html",
                    partial="errors/_error.html",
                    context={"title": title, "message": message},
                    status_code=status_code,
                )
            return await handler(request, exc)

        return wrapper

    return decorator


async def dashboard_context(
    request: Request,
    companion_service: CompanionServiceDependency,
    *,
    form_values: dict[str, str] | None = None,
    form_errors: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "request": request,
        "companions": await companion_service.list(),
        "form_values": form_values or {},
        "form_errors": form_errors or {},
    }


async def detail_context(
    request: Request,
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
    conversation_service: ConversationServiceDependency,
    *,
    editing: bool = False,
    form_values: dict[str, str] | None = None,
    form_errors: dict[str, str] | None = None,
) -> dict[str, object]:
    companion = await companion_service.get(companion_id)
    return {
        "request": request,
        "companion": companion,
        "conversations": await conversation_service.list_for_companion(companion_id),
        "editing": editing,
        "form_values": form_values
        or {
            "name": companion.name,
            "personality": companion.personality,
        },
        "form_errors": form_errors or {},
    }


async def chat_context(
    request: Request,
    conversation_id: UUID,
    companion_service: CompanionServiceDependency,
    conversation_service: ConversationServiceDependency,
    *,
    form_values: dict[str, str] | None = None,
    form_errors: dict[str, str] | None = None,
    chat_error: str | None = None,
) -> dict[str, object]:
    conversation = await conversation_service.get(conversation_id)
    companion = await companion_service.get(conversation.companion_id)
    return {
        "request": request,
        "conversation": conversation,
        "companion": companion,
        "messages": await conversation_service.list_messages(conversation_id),
        "form_values": form_values or {},
        "form_errors": form_errors or {},
        "chat_error": chat_error,
    }


@router.get("")
async def dashboard(
    request: Request,
    companion_service: CompanionServiceDependency,
) -> Response:
    context = await dashboard_context(request, companion_service)
    return template_response(
        request,
        page="companions/index.html",
        partial="companions/_dashboard.html",
        context=context,
    )


@router.post("/companions")
async def create_companion(
    request: Request,
    companion_service: CompanionServiceDependency,
    name: Annotated[str, Form()] = "",
    personality: Annotated[str, Form()] = "",
) -> Response:
    values = {"name": name, "personality": personality}
    try:
        payload = CompanionCreate.model_validate(values)
    except ValidationError as exc:
        context = await dashboard_context(
            request,
            companion_service,
            form_values=values,
            form_errors=validation_errors(exc),
        )
        return template_response(
            request,
            page="companions/index.html",
            partial="companions/_dashboard.html",
            context=context,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    companion = await companion_service.create(payload)
    if not is_htmx(request):
        return RedirectResponse(
            url=f"/ui/companions/{companion.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    context = await dashboard_context(request, companion_service)
    return template_response(
        request,
        page="companions/index.html",
        partial="companions/_dashboard.html",
        context=context,
        status_code=status.HTTP_201_CREATED,
    )


@router.get("/companions/{companion_id}")
async def companion_detail(
    request: Request,
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
    conversation_service: ConversationServiceDependency,
) -> Response:
    context = await detail_context(
        request,
        companion_id,
        companion_service,
        conversation_service,
    )
    return template_response(
        request,
        page="companions/detail.html",
        partial="companions/_detail.html",
        context=context,
    )


@router.get("/companions/{companion_id}/edit")
async def edit_companion_form(
    request: Request,
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
    conversation_service: ConversationServiceDependency,
) -> Response:
    context = await detail_context(
        request,
        companion_id,
        companion_service,
        conversation_service,
        editing=True,
    )
    return template_response(
        request,
        page="companions/detail.html",
        partial="companions/_detail.html",
        context=context,
    )


@router.post("/companions/{companion_id}/edit")
async def update_companion(
    request: Request,
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
    conversation_service: ConversationServiceDependency,
    name: Annotated[str, Form()] = "",
    personality: Annotated[str, Form()] = "",
) -> Response:
    values = {"name": name, "personality": personality}
    try:
        payload = CompanionUpdate.model_validate(values)
    except ValidationError as exc:
        context = await detail_context(
            request,
            companion_id,
            companion_service,
            conversation_service,
            editing=True,
            form_values=values,
            form_errors=validation_errors(exc),
        )
        return template_response(
            request,
            page="companions/detail.html",
            partial="companions/_detail.html",
            context=context,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    _ = await companion_service.update(companion_id, payload)
    if not is_htmx(request):
        return RedirectResponse(
            url=f"/ui/companions/{companion_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    context = await detail_context(
        request,
        companion_id,
        companion_service,
        conversation_service,
    )
    return template_response(
        request,
        page="companions/detail.html",
        partial="companions/_detail.html",
        context=context,
    )


async def delete_companion_response(
    request: Request,
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
) -> Response:
    await companion_service.delete(companion_id)
    if not is_htmx(request):
        return RedirectResponse(url="/ui", status_code=status.HTTP_303_SEE_OTHER)

    context = await dashboard_context(request, companion_service)
    response = template_response(
        request,
        page="companions/index.html",
        partial="companions/_dashboard.html",
        context=context,
    )
    response.headers["HX-Push-Url"] = "/ui"
    return response


@router.delete("/companions/{companion_id}")
async def delete_companion_htmx(
    request: Request,
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
) -> Response:
    return await delete_companion_response(request, companion_id, companion_service)


@router.post("/companions/{companion_id}/delete")
async def delete_companion_fallback(
    request: Request,
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
) -> Response:
    return await delete_companion_response(request, companion_id, companion_service)


@router.post("/companions/{companion_id}/conversations")
async def create_conversation(
    request: Request,
    companion_id: UUID,
    conversation_service: ConversationServiceDependency,
) -> Response:
    conversation = await conversation_service.create(companion_id)
    url = f"/ui/conversations/{conversation.id}"
    if not is_htmx(request):
        return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"HX-Redirect": url})


@router.get("/conversations/{conversation_id}")
async def chat(
    request: Request,
    conversation_id: UUID,
    companion_service: CompanionServiceDependency,
    conversation_service: ConversationServiceDependency,
) -> Response:
    context = await chat_context(
        request,
        conversation_id,
        companion_service,
        conversation_service,
    )
    return template_response(
        request,
        page="chat/index.html",
        partial="chat/_region.html",
        context=context,
    )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    request: Request,
    conversation_id: UUID,
    companion_service: CompanionServiceDependency,
    conversation_service: ConversationServiceDependency,
    chat_service: ChatServiceDependency,
    content: Annotated[str, Form()] = "",
) -> Response:
    values = {"content": content}
    try:
        payload = MessageCreate.model_validate(values)
    except ValidationError as exc:
        context = await chat_context(
            request,
            conversation_id,
            companion_service,
            conversation_service,
            form_values=values,
            form_errors=validation_errors(exc),
        )
        return template_response(
            request,
            page="chat/index.html",
            partial="chat/_region.html",
            context=context,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    try:
        _ = await chat_service.send_message(conversation_id, payload.content)
    except LLMProviderError:
        context = await chat_context(
            request,
            conversation_id,
            companion_service,
            conversation_service,
            chat_error=(
                "The reply could not be generated. Your message was saved; please try again."
            ),
        )
        return template_response(
            request,
            page="chat/index.html",
            partial="chat/_region.html",
            context=context,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    if not is_htmx(request):
        return RedirectResponse(
            url=f"/ui/conversations/{conversation_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    context = await chat_context(
        request,
        conversation_id,
        companion_service,
        conversation_service,
    )
    response = template_response(
        request,
        page="chat/index.html",
        partial="chat/_region.html",
        context=context,
        status_code=status.HTTP_201_CREATED,
    )
    response.headers["HX-Trigger-After-Settle"] = "chatUpdated"
    return response
