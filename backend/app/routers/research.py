"""SSE proxy: persists user/assistant messages and streams agent events to the client."""
import json
import logging
import uuid
from collections.abc import AsyncIterator

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


def _sse(event: str, data: str) -> bytes:
    """Format a single SSE frame. `data` may be raw JSON; emit as-is, no double-encoding."""
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


@router.post("/{conv_id}/query")
async def query_conversation(
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
    db.refresh(conv)

    history: list[dict[str, str]] = [
        {"role": m.role.lower(), "content": m.content or ""}
        for m in db.query(Message)
        .filter(Message.conversation_id == conv.id, Message.id != user_msg.id)
        .order_by(Message.created_at.asc())
        .all()
    ]

    user_msg_id = user_msg.id
    user_msg_created = user_msg.created_at.isoformat()
    conv_id_val = conv.id
    query_text = req.query

    async def generator() -> AsyncIterator[bytes]:
        yield _sse(
            "user_message", json.dumps({"id": str(user_msg_id), "createdAt": user_msg_created})
        )

        final_text = ""
        final_blocks: list = []
        final_sources: list = []
        final_follow_ups: list = []
        had_error = False
        error_msg = ""

        try:
            async for ev in stream_research(query_text, history):
                if await request.is_disconnected():
                    log.info("client disconnected mid-stream")
                    break

                yield _sse(ev.name, ev.data)

                try:
                    node = json.loads(ev.data)
                except json.JSONDecodeError:
                    continue

                if ev.name == "blocks":
                    data = node.get("data") or {}
                    blocks = data.get("blocks")
                    if isinstance(blocks, list):
                        final_blocks = blocks
                        for b in blocks:
                            if isinstance(b, dict) and b.get("template_id") == "markdown":
                                final_text = (b.get("data") or {}).get("content", "") or ""
                                break
                    sources = data.get("sources")
                    if isinstance(sources, list):
                        final_sources = sources
                    fups = data.get("follow_ups")
                    if isinstance(fups, list):
                        final_follow_ups = fups
                elif ev.name == "clarification":
                    final_text = node.get("content", "") or ""
                elif ev.name == "error":
                    had_error = True
                    error_msg = node.get("content", "Unknown error") or "Unknown error"

        except Exception as e:
            log.exception("research stream failed")
            yield _sse("error", json.dumps({"status": "failed", "content": str(e)}))
            return

        # Persist assistant message in a fresh session — the request-scoped one is closed by now.
        with SessionLocal() as persist_db:
            assistant = Message(
                conversation_id=conv_id_val,
                role=Role.ASSISTANT.value,
                content=error_msg if had_error else final_text,
                blocks=final_blocks or None,
                sources=final_sources or None,
                follow_ups=final_follow_ups or None,
            )
            persist_db.add(assistant)
            conv_row = persist_db.get(Conversation, conv_id_val)
            if conv_row is not None:
                from datetime import datetime, timezone
                conv_row.updated_at = datetime.now(timezone.utc)
            persist_db.commit()
            persist_db.refresh(assistant)
            yield _sse("persisted", json.dumps({"messageId": str(assistant.id)}))

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
