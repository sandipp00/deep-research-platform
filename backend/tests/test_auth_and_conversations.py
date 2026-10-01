import uuid

from conftest import auth_headers, register


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_register_login_me(client):
    reg = register(client, "Alice@Example.com", name="Alice")
    assert reg["email"] == "alice@example.com"
    assert reg["token"]

    dup = client.post(
        "/api/auth/register", json={"email": "alice@example.com", "password": "password123", "name": "A"}
    )
    assert dup.status_code == 409

    bad = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrongpass"})
    assert bad.status_code == 401

    login = client.post("/api/auth/login", json={"email": "ALICE@example.com", "password": "password123"})
    assert login.status_code == 200
    token = login.json()["token"]

    me = client.get("/api/auth/me", headers=auth_headers(token))
    assert me.status_code == 200
    assert me.json() == {"id": reg["id"], "email": "alice@example.com", "name": "Alice"}


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth_headers("garbage")).status_code == 401


def test_register_validation(client):
    r = client.post("/api/auth/register", json={"email": "x@example.com", "password": "short", "name": "X"})
    assert r.status_code == 422


def test_conversation_crud_and_rename_validation(client):
    token = register(client, "bob@example.com")["token"]
    h = auth_headers(token)

    created = client.post("/api/conversations", json={}, headers=h)
    assert created.status_code == 200
    conv = created.json()
    assert conv["title"] == "New chat"
    assert {"id", "title", "createdAt", "updatedAt"} <= conv.keys()

    assert client.patch(f"/api/conversations/{conv['id']}", json={"title": "   "}, headers=h).status_code == 422
    assert client.patch(f"/api/conversations/{conv['id']}", json={"title": ""}, headers=h).status_code == 422
    assert client.patch(f"/api/conversations/{conv['id']}", json={}, headers=h).status_code == 422
    assert client.patch(f"/api/conversations/{conv['id']}", json={"title": None}, headers=h).status_code == 422
    assert (
        client.patch(f"/api/conversations/{conv['id']}", json={"title": "x" * 201}, headers=h).status_code == 422
    )

    ok = client.patch(f"/api/conversations/{conv['id']}", json={"title": "  Renamed  "}, headers=h)
    assert ok.status_code == 204
    assert client.get(f"/api/conversations/{conv['id']}", headers=h).json()["title"] == "Renamed"

    listing = client.get("/api/conversations", headers=h).json()
    assert [c["id"] for c in listing] == [conv["id"]]

    assert client.delete(f"/api/conversations/{conv['id']}", headers=h).status_code == 204
    assert client.get(f"/api/conversations/{conv['id']}", headers=h).status_code == 404


def test_ownership_isolation(client):
    a = auth_headers(register(client, "owner@example.com")["token"])
    b = auth_headers(register(client, "intruder@example.com")["token"])

    conv_id = client.post("/api/conversations", json={"title": "Private"}, headers=a).json()["id"]

    assert client.get("/api/conversations", headers=b).json() == []
    assert client.get(f"/api/conversations/{conv_id}", headers=b).status_code == 404
    assert client.get(f"/api/conversations/{conv_id}/messages", headers=b).status_code == 404
    assert client.patch(f"/api/conversations/{conv_id}", json={"title": "pwned"}, headers=b).status_code == 404
    assert client.delete(f"/api/conversations/{conv_id}", headers=b).status_code == 404
    assert client.post(f"/api/conversations/{conv_id}/query", json={"query": "hi"}, headers=b).status_code == 404

    assert client.get(f"/api/conversations/{conv_id}", headers=a).json()["title"] == "Private"
    assert client.get(f"/api/conversations/{conv_id}/messages", headers=a).json() == []
    assert client.get(f"/api/conversations/{uuid.uuid4()}", headers=a).status_code == 404


def test_messages_endpoint_accepts_object_sources(client):
    from app.db import SessionLocal
    from app.models import Message, Role

    h = auth_headers(register(client, "src@example.com")["token"])
    conv_id = client.post("/api/conversations", json={}, headers=h).json()["id"]

    sources = [
        {"url": "https://example.com/a", "title": "A", "meta": {"rank": 1}},
        "https://example.com/plain",
        {"url": "https://example.com/b"},
    ]
    with SessionLocal() as db:
        db.add(Message(conversation_id=uuid.UUID(conv_id), role=Role.USER.value, content="q"))
        db.commit()
        db.add(
            Message(
                conversation_id=uuid.UUID(conv_id),
                role=Role.ASSISTANT.value,
                content="answer",
                blocks=[{"template_id": "markdown", "data": {"content": "answer"}}],
                sources=sources,
                follow_ups=[{"text": "more?"}, "plain?"],
            )
        )
        db.commit()

    r = client.get(f"/api/conversations/{conv_id}/messages", headers=h)
    assert r.status_code == 200, r.text
    msgs = r.json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["sources"] is None
    assert msgs[1]["sources"] == sources
    assert msgs[1]["followUps"] == [{"text": "more?"}, "plain?"]
