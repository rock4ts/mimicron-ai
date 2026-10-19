# Web UI tests are disabled while the HTML router is commented out.
# from uuid import UUID
#
# from httpx import AsyncClient
# from sqlalchemy.ext.asyncio import AsyncSession
#
# from app.models.companion import Companion
# from app.models.conversation import Conversation
# from tests.functional.fakes import FakeLLMController
#
# HTMX_HEADERS = {"HX-Request": "true"}
#
#
# async def create_companion(session: AsyncSession) -> Companion:
#     companion = Companion(
#         name="Nova",
#         personality="Calm, curious, and a little sarcastic.",
#     )
#     session.add(companion)
#     await session.commit()
#     await session.refresh(companion)
#     return companion
#
#
# async def create_conversation(session: AsyncSession, companion_id: UUID) -> Conversation:
#     conversation = Conversation(companion_id=companion_id)
#     session.add(conversation)
#     await session.commit()
#     await session.refresh(conversation)
#     return conversation
#
#
# async def test_web_dashboard_and_static_assets(client: AsyncClient) -> None:
#     response = await client.get("/")
#     assert response.status_code == 307
#     assert response.headers["location"] == "/ui"
#
#     response = await client.get("/ui")
#     assert response.status_code == 200
#     assert response.headers["content-type"].startswith("text/html")
#     assert "Who do you want to talk to?" in response.text
#     assert 'action="/ui/companions"' in response.text
#
#     stylesheet = await client.get("/static/css/main.css")
#     assert stylesheet.status_code == 200
#     assert "--primary:" in stylesheet.text
#
#     javascript = await client.get("/static/js/app.js")
#     assert javascript.status_code == 200
#     assert "htmx:beforeSwap" in javascript.text
#
#
# async def test_web_companion_crud_and_validation(
#     client: AsyncClient,
#     db_session: AsyncSession,
# ) -> None:
#     invalid = await client.post(
#         "/ui/companions",
#         data={"name": "  ", "personality": "Friendly"},
#         headers=HTMX_HEADERS,
#     )
#     assert invalid.status_code == 422
#     assert "must not be empty" in invalid.text
#     assert "<html" not in invalid.text
#
#     created = await client.post(
#         "/ui/companions",
#         data={"name": "Nova", "personality": "Calm and curious."},
#         headers=HTMX_HEADERS,
#     )
#     assert created.status_code == 201
#     assert "Nova" in created.text
#     assert "<html" not in created.text
#
#     companion = (await db_session.execute(Companion.__table__.select())).first()
#     assert companion is not None
#     companion_id = companion.id
#
#     detail = await client.get(f"/ui/companions/{companion_id}")
#     assert detail.status_code == 200
#     assert "Calm and curious." in detail.text
#
#     updated = await client.post(
#         f"/ui/companions/{companion_id}/edit",
#         data={"name": "Nova Prime", "personality": "Warm and direct."},
#         headers=HTMX_HEADERS,
#     )
#     assert updated.status_code == 200
#     assert "Nova Prime" in updated.text
#     assert "Warm and direct." in updated.text
#
#     deleted = await client.delete(
#         f"/ui/companions/{companion_id}",
#         headers=HTMX_HEADERS,
#     )
#     assert deleted.status_code == 200
#     assert deleted.headers["hx-push-url"] == "/ui"
#     assert "No companions yet" in deleted.text
#
#
# async def test_web_conversation_history_and_chat(
#     client: AsyncClient,
#     db_session: AsyncSession,
#     fake_llm: FakeLLMController,
# ) -> None:
#     companion = await create_companion(db_session)
#     conversation = await create_conversation(db_session, companion.id)
#
#     detail = await client.get(f"/ui/companions/{companion.id}")
#     assert detail.status_code == 200
#     assert f"/ui/conversations/{conversation.id}" in detail.text
#
#     await fake_llm.configure(responses=["Good to see you."])
#     response = await client.post(
#         f"/ui/conversations/{conversation.id}/messages",
#         data={"content": "Hello, Nova!"},
#         headers=HTMX_HEADERS,
#     )
#     assert response.status_code == 201
#     assert "<html" not in response.text
#     assert "Hello, Nova!" in response.text
#     assert "Good to see you." in response.text
#     assert response.headers["hx-trigger-after-settle"] == "chatUpdated"
#
#
# async def test_web_create_conversation_redirects(
#     client: AsyncClient,
#     db_session: AsyncSession,
# ) -> None:
#     companion = await create_companion(db_session)
#
#     fallback = await client.post(f"/ui/companions/{companion.id}/conversations")
#     assert fallback.status_code == 303
#     assert fallback.headers["location"].startswith("/ui/conversations/")
#
#     htmx = await client.post(
#         f"/ui/companions/{companion.id}/conversations",
#         headers=HTMX_HEADERS,
#     )
#     assert htmx.status_code == 204
#     assert htmx.headers["hx-redirect"].startswith("/ui/conversations/")
#
#
# async def test_web_validation_and_llm_failure_are_html(
#     client: AsyncClient,
#     db_session: AsyncSession,
#     fake_llm: FakeLLMController,
# ) -> None:
#     companion = await create_companion(db_session)
#     conversation = await create_conversation(db_session, companion.id)
#
#     invalid = await client.post(
#         f"/ui/conversations/{conversation.id}/messages",
#         data={"content": "  "},
#         headers=HTMX_HEADERS,
#     )
#     assert invalid.status_code == 422
#     assert "must not be empty" in invalid.text
#     assert invalid.headers["content-type"].startswith("text/html")
#
#     await fake_llm.configure(error="upstream failed")
#     failed = await client.post(
#         f"/ui/conversations/{conversation.id}/messages",
#         data={"content": "Are you there?"},
#         headers=HTMX_HEADERS,
#     )
#     assert failed.status_code == 502
#     assert "Your message was saved" in failed.text
#     assert "Are you there?" in failed.text
#     assert failed.headers["content-type"].startswith("text/html")
#
#
# async def test_web_missing_resource_renders_html(client: AsyncClient) -> None:
#     missing = await client.get("/ui/companions/00000000-0000-0000-0000-000000000000")
#     assert missing.status_code == 404
#     assert missing.headers["content-type"].startswith("text/html")
#     assert "Companion not found" in missing.text
#
#     malformed = await client.get("/ui/companions/not-a-uuid")
#     assert malformed.status_code == 422
#     assert malformed.headers["content-type"].startswith("text/html")
#     assert "Invalid request" in malformed.text
