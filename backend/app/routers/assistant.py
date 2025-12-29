from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
import uuid

router = APIRouter()

_THREADS = {}


class ThreadOut(BaseModel):
    id: str
    created_at: datetime


class MessageIn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


class MessageOut(MessageIn):
    id: str
    created_at: datetime


@router.post("/assistant/threads", response_model=ThreadOut)
def create_thread():
    tid = str(uuid.uuid4())
    _THREADS[tid] = []
    return ThreadOut(id=tid, created_at=datetime.utcnow())


@router.get("/assistant/threads/{thread_id}/messages", response_model=List[MessageOut])
def list_messages(thread_id: str):
    return _THREADS.get(thread_id, [])


@router.post("/assistant/threads/{thread_id}/messages", response_model=MessageOut)
def add_message(thread_id: str, payload: MessageIn):
    if thread_id not in _THREADS:
        _THREADS[thread_id] = []
    msg = MessageOut(
        id=str(uuid.uuid4()), created_at=datetime.utcnow(), **payload.model_dump()
    )
    _THREADS[thread_id].append(msg)

    if payload.role == "user":
        reply = MessageOut(
            id=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            role="assistant",
            content="Got it. (Assistant skeleton) Next: connect OpenAI + retrieval + tool-calling.",
        )
        _THREADS[thread_id].append(reply)
        return reply

    return msg
