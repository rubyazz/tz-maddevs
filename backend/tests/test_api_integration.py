"""API integration tests: real PostgreSQL + full ASGI app (lifespan on).

HTTP probing is mocked at the httpx layer with respx; everything else —
routing, auth, ownership, validation, persistence, notifications — runs
for real.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx
from asgi_lifespan import LifespanManager

from app.db import Base, make_engine
from app.main import app
from tests.conftest import TEST_DATABASE_URL, requires_db

pytestmark = [pytest.mark.asyncio, requires_db]


@pytest_asyncio.fixture
async def client():
    engine = make_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    await engine.dispose()



async def _auth(client: httpx.AsyncClient, email: str = "user@example.com") -> str:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 201
    return response.json()["token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_register_login_me(client):
    token = await _auth(client)
    me = await client.get("/api/me", headers=_auth_headers(token))
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"

    dup = await client.post(
        "/api/auth/register", json={"email": "user@example.com", "password": "password123"}
    )
    assert dup.status_code == 409

    bad = await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401

    no_token = await client.get("/api/me")
    assert no_token.status_code == 401


async def test_group_and_check_crud_with_validation(client):
    token = await _auth(client)
    headers = _auth_headers(token)

    group = await client.post("/api/groups", json={"name": "Prod"}, headers=headers)
    assert group.status_code == 201
    group_id = group.json()["id"]

    slug = await client.post(f"/api/groups/{group_id}/public-slug/generate", headers=headers)
    assert slug.status_code == 200 and slug.json()["public_slug"]

    bad_interval = await client.post(
        "/api/checks",
        json={
            "group_id": group_id,
            "name": "x",
            "url": "http://example.com",
            "interval_seconds": 29,  # below the 30s floor
            "timeout_seconds": 10,
        },
        headers=headers,
    )
    assert bad_interval.status_code == 422

    check = await client.post(
        "/api/checks",
        json={
            "group_id": group_id,
            "name": "site",
            "url": "http://example.com/health",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "failure_threshold": 1,
            "show_on_public": True,
        },
        headers=headers,
    )
    assert check.status_code == 201
    check_id = check.json()["id"]
    assert check.json()["state"] == "unknown"

    paused = await client.post(f"/api/checks/{check_id}/pause", headers=headers)
    assert paused.status_code == 200 and paused.json()["paused"] is True
    resumed = await client.post(f"/api/checks/{check_id}/resume", headers=headers)
    assert resumed.status_code == 200 and resumed.json()["paused"] is False

    deleted = await client.delete(f"/api/checks/{check_id}", headers=headers)
    assert deleted.status_code == 204


async def test_ownership_isolation(client):
    token_a = await _auth(client, "a@example.com")
    token_b = await _auth(client, "b@example.com")

    group = await client.post(
        "/api/groups", json={"name": "A's group"}, headers=_auth_headers(token_a)
    )
    group_id = group.json()["id"]

    for method, path in [
        ("PATCH", f"/api/groups/{group_id}"),
        ("DELETE", f"/api/groups/{group_id}"),
    ]:
        response = await client.request(method, path, json={"name": "stolen"},
                                        headers=_auth_headers(token_b))
        assert response.status_code == 404, f"{method} leaked another owner's group"

    overview_b = await client.get("/api/overview", headers=_auth_headers(token_b))
    assert overview_b.status_code == 200
    assert overview_b.json()["groups"] == []


@respx.mock
async def test_manual_run_incident_and_letters(client):
    token = await _auth(client)
    headers = _auth_headers(token)
    group = await client.post(
        "/api/groups", json={"name": "G"}, headers=headers
    )
    group_id = group.json()["id"]
    await client.post(
        f"/api/groups/{group_id}/emails", json={"email": "alerts@example.com"}, headers=headers
    )
    check = await client.post(
        "/api/checks",
        json={
            "group_id": group_id,
            "name": "watched",
            "url": "http://watched.example.com",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "failure_threshold": 2,
        },
        headers=headers,
    )
    check_id = check.json()["id"]
    route = respx.get("http://watched.example.com").mock(return_value=httpx.Response(500))

    # two failures reach the threshold → incident + one DOWN letter
    for _ in range(2):
        response = await client.post(f"/api/checks/{check_id}/run", headers=headers)
        assert response.status_code == 200
    detail = await client.get(f"/api/checks/{check_id}", headers=headers)
    body = detail.json()
    assert body["state"] == "down"
    assert body["open_incident"] is not None

    # extra failures — the letter count must not grow
    await client.post(f"/api/checks/{check_id}/run", headers=headers)
    mailbox = await client.get("/api/mailbox", headers=headers)
    down_letters = [m for m in mailbox.json()["items"] if m["kind"] == "down"]
    assert len(down_letters) == 1

    # recovery → incident closed + one UP letter
    route.mock(return_value=httpx.Response(200, text="ok"))
    response = await client.post(f"/api/checks/{check_id}/run", headers=headers)
    assert response.json()["state"] == "up"
    mailbox = await client.get("/api/mailbox", headers=headers)
    items = mailbox.json()["items"]
    assert len([m for m in items if m["kind"] == "up"]) == 1
    assert len([m for m in items if m["kind"] == "down"]) == 1

    detail = await client.get(f"/api/checks/{check_id}", headers=headers)
    assert detail.json()["incidents"][0]["ended_at"] is not None
    assert detail.json()["incidents"][0]["duration_s"] is not None


@respx.mock
async def test_manual_run_expected_body_mismatch(client):
    token = await _auth(client)
    headers = _auth_headers(token)
    group = await client.post("/api/groups", json={"name": "G"}, headers=headers)
    check = await client.post(
        "/api/checks",
        json={
            "group_id": group.json()["id"],
            "name": "body-check",
            "url": "http://body.example.com",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "expected_body": "PONG",
        },
        headers=headers,
    )
    respx.get("http://body.example.com").mock(return_value=httpx.Response(200, text="PONG!"))
    response = await client.post(f"/api/checks/{check.json()['id']}/run", headers=headers)
    assert response.json()["last_ok"] is True

    respx.get("http://body.example.com").mock(return_value=httpx.Response(200, text="WRONG"))
    response = await client.post(f"/api/checks/{check.json()['id']}/run", headers=headers)
    assert response.json()["last_ok"] is False
    assert "substring" in response.json()["last_error"]


async def test_maintenance_validation_and_listing(client):
    token = await _auth(client)
    headers = _auth_headers(token)
    group = await client.post("/api/groups", json={"name": "G"}, headers=headers)
    group_id = group.json()["id"]
    check = await client.post(
        "/api/checks",
        json={
            "group_id": group_id,
            "name": "c",
            "url": "http://c.example.com",
            "interval_seconds": 60,
            "timeout_seconds": 5,
        },
        headers=headers,
    )
    check_id = check.json()["id"]

    both = await client.post(
        "/api/maintenance-windows",
        json={
            "check_id": check_id,
            "group_id": group_id,
            "starts_at": "2026-10-06T12:00:00+00:00",
            "ends_at": "2026-10-06T13:00:00+00:00",
        },
        headers=headers,
    )
    assert both.status_code == 422

    valid = await client.post(
        "/api/maintenance-windows",
        json={
            "group_id": group_id,
            "starts_at": "2026-10-06T12:00:00+00:00",
            "ends_at": "2026-10-06T13:00:00+00:00",
            "note": "upgrade",
        },
        headers=headers,
    )
    assert valid.status_code == 201
    assert valid.json()["group_name"] == "G"

    listing = await client.get("/api/maintenance-windows", headers=headers)
    assert listing.status_code == 200 and len(listing.json()) == 1


async def test_public_page_shows_only_published(client):
    token = await _auth(client)
    headers = _auth_headers(token)
    group = await client.post("/api/groups", json={"name": "Public group"}, headers=headers)
    group_id = group.json()["id"]
    slug = (await client.post(f"/api/groups/{group_id}/public-slug/generate", headers=headers)).json()[
        "public_slug"
    ]

    for name, public in (("visible", True), ("hidden", False)):
        await client.post(
            "/api/checks",
            json={
                "group_id": group_id,
                "name": name,
                "url": "http://x.example.com",
                "interval_seconds": 60,
                "timeout_seconds": 5,
                "show_on_public": public,
            },
            headers=headers,
        )

    page = await client.get(f"/api/public/{slug}")
    assert page.status_code == 200
    names = [c["name"] for c in page.json()["checks"]]
    assert names == ["visible"]

    missing = await client.get("/api/public/no-such-slug")
    assert missing.status_code == 404
