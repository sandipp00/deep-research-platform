import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..deps import get_current_user
from ..models import Conversation, Message, Role, User
from ..research_client import stream_research
from ..schemas import QueryRequest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["research"])

HISTORY_LIMIT = 20
GENERIC_ERROR = "The research service is currently unavailable. Please try again later."


def _sse(event: str, data: str) -> bytes:
    payload = "".join(f"data: {line}\n" for line in data.split("\n"))
    return f"event: {event}\n{payload}\n".encode()


def _owned(db: Session, user: User, conv_id: uuid.UUID) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == user.id)
        .one_or_none()
    )
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


def _load_history(db: Session, conv_id: uuid.UUID, exclude_id: uuid.UUID) -> list[dict[str, str]]:
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id, Message.id != exclude_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    return [{"role": m.role.lower(), "content": m.content or ""} for m in reversed(rows)]


def _persist_assistant(conv_id: uuid.UUID, state: dict[str, Any]) -> str:
    with SessionLocal() as db:
        assistant = Message(
            conversation_id=conv_id,
            role=Role.ASSISTANT.value,
            content=state["error_msg"] if state["had_error"] else state["text"],
            blocks=state["blocks"] or None,
            sources=state["sources"] or None,
            follow_ups=state["follow_ups"] or None,
        )
        db.add(assistant)
        conv_row = db.get(Conversation, conv_id)
        if conv_row is not None:
            conv_row.updated_at = datetime.now(timezone.utc)
        db.commit()
        state["persisted_id"] = str(assistant.id)
        return state["persisted_id"]


def _apply_event(state: dict[str, Any], name: str, raw: str) -> None:
    try:
        node = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(node, dict):
        return
    if name == "blocks":
        data = node.get("data") or {}
        if not isinstance(data, dict):
            return
        blocks = data.get("blocks")
        if isinstance(blocks, list):
            state["blocks"] = blocks
            for b in blocks:
                if isinstance(b, dict) and b.get("template_id") == "markdown":
                    state["text"] = (b.get("data") or {}).get("content", "") or ""
                    break
        sources = data.get("sources")
        if isinstance(sources, list):
            state["sources"] = sources
        fups = data.get("follow_ups")
        if isinstance(fups, list):
            state["follow_ups"] = fups
    elif name == "clarification":
        state["text"] = node.get("content", "") or ""
    elif name == "error":
        state["had_error"] = True
        state["error_msg"] = node.get("content", "Unknown error") or "Unknown error"


@router.post("/{conv_id}/query")
def query_conversation(
    conv_id: uuid.UUID,
    req: QueryRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    conv = _owned(db, user, conv_id)

    user_msg = Message(conversation_id=conv.id, role=Role.USER.value, content=req.query)
    db.add(user_msg)
    if conv.title == "New chat":
        conv.title = req.query[:57] + "..." if len(req.query) > 60 else req.query
    db.commit()
    db.refresh(user_msg)

    history = _load_history(db, conv.id, user_msg.id)
    user_msg_id = user_msg.id
    user_msg_created = user_msg.created_at.isoformat()
    conv_id_val = conv.id
    query_text = req.query
    db.close()

    async def generator() -> AsyncIterator[bytes]:
        state: dict[str, Any] = {
            "text": "",
            "blocks": [],
            "sources": [],
            "follow_ups": [],
            "had_error": False,
            "error_msg": "",
            "persisted_id": None,
        }

        async def persist() -> str:
            return await anyio.to_thread.run_sync(_persist_assistant, conv_id_val, state)

        try:
            yield _sse(
                "user_message", json.dumps({"id": str(user_msg_id), "createdAt": user_msg_created})
            )
            try:
                async for ev in stream_research(query_text, history):
                    if await request.is_disconnected():
                        log.info("client disconnected mid-stream conversation=%s", conv_id_val)
                        break
                    yield _sse(ev.name, ev.data)
                    _apply_event(state, ev.name, ev.data)
            except Exception:
                log.exception("research stream failed conversation=%s", conv_id_val)
                state["had_error"] = True
                state["error_msg"] = GENERIC_ERROR
                yield _sse("error", json.dumps({"status": "failed", "content": GENERIC_ERROR}))

            message_id = await persist()
            yield _sse("persisted", json.dumps({"messageId": message_id}))
        finally:
            if state["persisted_id"] is None and (
                state["text"] or state["blocks"] or state["had_error"]
            ):
                with anyio.CancelScope(shield=True):
                    try:
                        await persist()
                    except Exception:
                        log.exception("failed to persist partial assistant message conversation=%s", conv_id_val)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
