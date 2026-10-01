import json
import time
import uuid

import httpx

from conftest import AGENT_REQUESTS, LEAK_MARKER, OK_BLOCKS, auth_headers


def _parse_sse(raw: str) -> list[tuple[str, str]]:
    events = []
    for block in raw.strip().split("\n\n"):
        name, data = None, []
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data.append(line[6:])
        if name:
            events.append((name, "\n".join(data)))
    return events


def _setup(base: str, email: str) -> tuple[dict, str]:
    with httpx.Client(base_url=base, timeout=30) as c:
        r = c.post("/api/auth/register", json={"email": email, "password": "password123", "name": "N"})
        assert r.status_code == 200, r.text
        h = auth_headers(r.json()["token"])
        conv_id = c.post("/api/conversations", json={}, headers=h).json()["id"]
    return h, conv_id


def _query(base: str, h: dict, conv_id: str, query: str) -> list[tuple[str, str]]:
    with httpx.Client(base_url=base, timeout=60) as c:
        r = c.post(f"/api/conversations/{conv_id}/query", json={"query": query}, headers=h)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/event-stream")
        return _parse_sse(r.text)


def _messages(base: str, h: dict, conv_id: str) -> list[dict]:
    with httpx.Client(base_url=base, timeout=30) as c:
        r = c.get(f"/api/conversations/{conv_id}/messages", headers=h)
        assert r.status_code == 200, r.text
        return r.json()


def test_query_happy_path_forwards_events_and_persists(live_backend):
    h, conv_id = _setup(live_backend, "happy@example.com")
    events = _query(live_backend, h, conv_id, "ok")
    names = [n for n, _ in events]
    assert names == ["user_message", "progress", "blocks", "done", "persisted"]

    user_msg = json.loads(events[0][1])
    assert uuid.UUID(user_msg["id"]) and user_msg["createdAt"]
    assert json.loads(events[2][1]) == OK_BLOCKS
    persisted_id = json.loads(events[-1][1])["messageId"]

    msgs = _messages(live_backend, h, conv_id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["id"] == user_msg["id"]
    assert msgs[0]["content"] == "ok"
    assistant = msgs[1]
    assert assistant["id"] == persisted_id
    assert assistant["content"] == "Final answer text"
    assert assistant["sources"] == OK_BLOCKS["data"]["sources"]
    assert assistant["followUps"] == ["What next?"]
    assert assistant["blocks"] == OK_BLOCKS["data"]["blocks"]

    with httpx.Client(base_url=live_backend) as c:
        assert c.get(f"/api/conversations/{conv_id}", headers=h).json()["title"] == "ok"


def test_query_agent_error_event_is_forwarded_and_saved(live_backend):
    h, conv_id = _setup(live_backend, "agenterr@example.com")
    events = _query(live_backend, h, conv_id, "agent-error")
    assert [n for n, _ in events] == ["user_message", "progress", "error", "persisted"]
    msgs = _messages(live_backend, h, conv_id)
    assert msgs[-1]["role"] == "assistant"
    assert msgs[-1]["content"] == "Agent could not complete"


def test_query_clarification_is_saved(live_backend):
    h, conv_id = _setup(live_backend, "clarify@example.com")
    events = _query(live_backend, h, conv_id, "clarify")
    assert [n for n, _ in events] == ["user_message", "progress", "clarification", "persisted"]
    assert _messages(live_backend, h, conv_id)[-1]["content"] == "Which one do you mean?"


def test_query_agent_http_failure_does_not_leak_details(live_backend, fake_agent):
    h, conv_id = _setup(live_backend, "leak@example.com")
    with httpx.Client(base_url=live_backend, timeout=60) as c:
        r = c.post(f"/api/conversations/{conv_id}/query", json={"query": "http500"}, headers=h)
    assert r.status_code == 200
    assert LEAK_MARKER not in r.text
    assert fake_agent not in r.text

    events = _parse_sse(r.text)
    assert [n for n, _ in events] == ["user_message", "error", "persisted"]
    err = json.loads(events[1][1])
    assert err["status"] == "failed"
    assert err["content"]

    saved = _messages(live_backend, h, conv_id)[-1]
    assert saved["role"] == "assistant"
    assert saved["content"] == err["content"]
    assert LEAK_MARKER not in saved["content"]
    assert fake_agent not in saved["content"]


def test_query_history_is_capped_to_last_20(live_backend):
    from app.db import SessionLocal
    from app.models import Message, Role

    h, conv_id = _setup(live_backend, "history@example.com")
    with SessionLocal() as db:
        for i in range(30):
            db.add(
                Message(
                    conversation_id=uuid.UUID(conv_id),
                    role=(Role.USER if i % 2 == 0 else Role.ASSISTANT).value,
                    content=f"m{i}",
                )
            )
            db.commit()

    _query(live_backend, h, conv_id, "ok")
    history = AGENT_REQUESTS[-1]["conversation_history"]
    assert len(history) == 20
    assert [m["content"] for m in history] == [f"m{i}" for i in range(10, 30)]
    assert history[0]["role"] == "user"
    assert AGENT_REQUESTS[-1]["query"] == "ok"


def test_query_persists_partial_result_on_client_disconnect(live_backend):
    h, conv_id = _setup(live_backend, "disconnect@example.com")
    seen = []
    with httpx.Client(base_url=live_backend, timeout=30) as c:
        with c.stream("POST", f"/api/conversations/{conv_id}/query", json={"query": "slow"}, headers=h) as r:
            assert r.status_code == 200
            for line in r.iter_lines():
                if line.startswith("event: "):
                    seen.append(line[7:])
                if "blocks" in seen and line == "":
                    break
    assert seen[:3] == ["user_message", "progress", "blocks"]

    deadline = time.time() + 15
    msgs: list[dict] = []
    while time.time() < deadline:
        msgs = _messages(live_backend, h, conv_id)
        if len(msgs) == 2:
            break
        time.sleep(0.2)

    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Final answer text"
    assert msgs[1]["sources"] == OK_BLOCKS["data"]["sources"]

    time.sleep(0.5)
    assert len(_messages(live_backend, h, conv_id)) == 2


def test_query_unknown_conversation_is_404(live_backend):
    h, _ = _setup(live_backend, "nf@example.com")
    with httpx.Client(base_url=live_backend, timeout=30) as c:
        r = c.post(f"/api/conversations/{uuid.uuid4()}/query", json={"query": "ok"}, headers=h)
    assert r.status_code == 404
