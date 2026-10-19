from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.companion import Companion
from app.models.conversation import Conversation
from tests.functional.fakes import FakeLLMController
from tests.functional.jwt import OTHER_USER_ID, auth_headers, mint_token


def _unauthorized(response: Response) -> None:
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    assert "detail" in response.json()


def _other_rsa_private_pem() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


async def test_health_is_public(http_client: AsyncClient) -> None:
    response = await http_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_echoes_supplied_request_id(http_client: AsyncClient) -> None:
    response = await http_client.get("/health", headers={"x-request-id": "test-correlation-123"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-correlation-123"


async def test_health_generates_request_id_when_missing(http_client: AsyncClient) -> None:
    response = await http_client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")


async def test_root_redirects_to_docs(http_client: AsyncClient) -> None:
    response = await http_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


async def test_docs_are_public(http_client: AsyncClient) -> None:
    response = await http_client.get("/docs")
    assert response.status_code == 200


async def test_openapi_documents_bearer_auth(http_client: AsyncClient) -> None:
    response = await http_client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    schemes = spec["components"]["securitySchemes"]
    assert any(scheme.get("scheme") == "bearer" for scheme in schemes.values())
    companions = spec["paths"]["/companions"]["get"]
    assert companions.get("security")


async def test_protected_routes_require_bearer(http_client: AsyncClient) -> None:
    _unauthorized(await http_client.get("/companions"))
    _unauthorized(await http_client.post("/companions", json={"name": "Nova", "personality": "x"}))


async def test_malformed_authorization_header(http_client: AsyncClient) -> None:
    _unauthorized(await http_client.get("/companions", headers={"Authorization": "Token abc"}))
    _unauthorized(await http_client.get("/companions", headers={"Authorization": "Bearer"}))
    _unauthorized(
        await http_client.get("/companions", headers={"Authorization": "Bearer not-a-jwt"})
    )


async def test_expired_token_is_rejected(http_client: AsyncClient) -> None:
    token = mint_token(expires_in_seconds=-60)
    _unauthorized(await http_client.get("/companions", headers=auth_headers(token)))


async def test_token_signed_by_another_key_is_rejected(http_client: AsyncClient) -> None:
    token = mint_token(private_key=_other_rsa_private_pem())
    _unauthorized(await http_client.get("/companions", headers=auth_headers(token)))


async def test_refresh_token_is_rejected(http_client: AsyncClient) -> None:
    token = mint_token(token_type="refresh")
    _unauthorized(await http_client.get("/companions", headers=auth_headers(token)))


async def test_token_with_missing_claims_is_rejected(http_client: AsyncClient) -> None:
    token = mint_token(omit={"tv", "is_superuser"})
    _unauthorized(await http_client.get("/companions", headers=auth_headers(token)))


async def test_token_with_invalid_sub_is_rejected(http_client: AsyncClient) -> None:
    token = mint_token(extra={"sub": "not-a-uuid"})
    _unauthorized(await http_client.get("/companions", headers=auth_headers(token)))


async def test_hs256_token_is_rejected(http_client: AsyncClient) -> None:
    token = mint_token(private_key=b"not-the-rsa-key-and-long-enough", algorithm="HS256")
    _unauthorized(await http_client.get("/companions", headers=auth_headers(token)))


async def test_valid_token_can_create_owned_companion(client: AsyncClient) -> None:
    response = await client.post(
        "/companions",
        json={"name": "Nova", "personality": "Спокойная и немного саркастичная."},
    )
    assert response.status_code == 201
    listed = await client.get("/companions")
    assert [item["id"] for item in listed.json()] == [response.json()["id"]]


async def test_users_cannot_see_each_others_companions(
    client: AsyncClient,
    http_client: AsyncClient,
    db_session: AsyncSession,
    user_id: UUID,
) -> None:
    owned = await client.post(
        "/companions",
        json={"name": "Mine", "personality": "Owned by the default user."},
    )
    assert owned.status_code == 201

    foreign = Companion(name="Theirs", personality="Owned by another user.", user_id=OTHER_USER_ID)
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    listed = await client.get("/companions")
    assert [item["id"] for item in listed.json()] == [owned.json()["id"]]

    other_headers = auth_headers(mint_token(sub=OTHER_USER_ID))
    other_list = await http_client.get("/companions", headers=other_headers)
    assert [item["id"] for item in other_list.json()] == [str(foreign.id)]


async def test_cross_user_companion_access_returns_404(
    client: AsyncClient,
    http_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    foreign = Companion(name="Theirs", personality="Owned by another user.", user_id=OTHER_USER_ID)
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    assert (await client.get(f"/companions/{foreign.id}")).status_code == 404
    assert (
        await client.patch(f"/companions/{foreign.id}", json={"name": "Hijacked"})
    ).status_code == 404
    assert (await client.delete(f"/companions/{foreign.id}")).status_code == 404
    assert (await client.post(f"/companions/{foreign.id}/conversations")).status_code == 404
    assert (await client.get(f"/companions/{foreign.id}/conversations")).status_code == 404

    other_headers = auth_headers(mint_token(sub=OTHER_USER_ID))
    visible = await http_client.get(f"/companions/{foreign.id}", headers=other_headers)
    assert visible.status_code == 200
    assert visible.json()["name"] == "Theirs"


async def test_cross_user_conversation_and_message_access_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_llm: FakeLLMController,
) -> None:
    foreign = Companion(name="Theirs", personality="Owned by another user.", user_id=OTHER_USER_ID)
    db_session.add(foreign)
    await db_session.flush()
    conversation = Conversation(companion_id=foreign.id)
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    await fake_llm.configure(responses=["should not be called"])
    assert (await client.get(f"/conversations/{conversation.id}")).status_code == 404
    assert (await client.get(f"/conversations/{conversation.id}/messages")).status_code == 404
    assert (
        await client.post(
            f"/conversations/{conversation.id}/messages",
            json={"content": "Привет"},
        )
    ).status_code == 404


async def test_legacy_unowned_companions_are_hidden(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    legacy = Companion(name="Legacy", personality="Created before ownership.", user_id=None)
    db_session.add(legacy)
    await db_session.commit()
    await db_session.refresh(legacy)

    listed = await client.get("/companions")
    assert listed.json() == []
    assert (await client.get(f"/companions/{legacy.id}")).status_code == 404
    assert (
        await client.patch(f"/companions/{legacy.id}", json={"name": "Claimed"})
    ).status_code == 404
    assert (await client.delete(f"/companions/{legacy.id}")).status_code == 404
    assert (await client.post(f"/companions/{legacy.id}/conversations")).status_code == 404
    assert (await client.get(f"/companions/{legacy.id}/conversations")).status_code == 404

    remaining = await db_session.get(Companion, legacy.id)
    assert remaining is not None
    assert remaining.user_id is None
    assert remaining.name == "Legacy"
