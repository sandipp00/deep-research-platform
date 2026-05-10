import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Conversation, Message, User
from ..schemas import ConversationDto, CreateConversationRequest, MessageDto, RenameConversationRequest

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _owned_or_404(db: Session, user: User, conv_id: uuid.UUID) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == user.id)
        .one_or_none()
    )
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


@router.get("", response_model=list[ConversationDto])
def list_conversations(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ConversationDto]:
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [ConversationDto.model_validate(c) for c in rows]


@router.post("", response_model=ConversationDto)
def create_conversation(
    req: CreateConversationRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDto:
    title = (req.title.strip() if req and req.title and req.title.strip() else "New chat")
    conv = Conversation(user_id=user.id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationDto.model_validate(conv)


@router.get("/{conv_id}", response_model=ConversationDto)
def get_conversation(
    conv_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ConversationDto:
    return ConversationDto.model_validate(_owned_or_404(db, user, conv_id))


@router.patch("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def rename_conversation(
    conv_id: uuid.UUID,
    req: RenameConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    conv = _owned_or_404(db, user, conv_id)
    if req.title and req.title.strip():
        conv.title = req.title.strip()
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conv_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    conv = _owned_or_404(db, user, conv_id)
    db.delete(conv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conv_id}/messages", response_model=list[MessageDto])
def list_messages(
    conv_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[MessageDto]:
    conv = _owned_or_404(db, user, conv_id)
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [
        MessageDto(
            id=m.id,
            role=m.role.lower() if isinstance(m.role, str) else m.role.name.lower(),
            content=m.content,
            blocks=m.blocks,
            sources=m.sources,
            follow_ups=m.follow_ups,
            created_at=m.created_at,
        )
        for m in rows
    ]
