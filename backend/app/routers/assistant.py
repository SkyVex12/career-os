from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

router = APIRouter()

# In-memory store (dev). Later: persist to SQLite.
_THREADS: Dict[str, Dict[str, Any]] = {}
# shape:
# _THREADS[tid] = {"id": tid, "title": "...", "created_at": dt, "updated_at": dt, "messages": [MessageOut...]}


class ThreadOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ThreadPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class MessageIn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


class MessageOut(MessageIn):
    id: str
    created_at: datetime


def _now():
    return datetime.now()


@router.get("/assistant/threads", response_model=List[ThreadOut])
def list_threads():
    # Sort newest first
    items = list(_THREADS.values())
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return [
        ThreadOut(
            id=t["id"],
            title=t["title"],
            created_at=t["created_at"],
            updated_at=t["updated_at"],
        )
        for t in items
    ]


@router.post("/assistant/threads", response_model=ThreadOut)
def create_thread():
    tid = str(uuid.uuid4())
    now = _now()
    _THREADS[tid] = {
        "id": tid,
        "title": "New chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    t = _THREADS[tid]
    return ThreadOut(
        id=t["id"],
        title=t["title"],
        created_at=t["created_at"],
        updated_at=t["updated_at"],
    )


@router.patch("/assistant/threads/{thread_id}", response_model=ThreadOut)
def rename_thread(thread_id: str, payload: ThreadPatch):
    if thread_id not in _THREADS:
        raise HTTPException(status_code=404, detail="Thread not found")
    _THREADS[thread_id]["title"] = payload.title.strip()
    _THREADS[thread_id]["updated_at"] = _now()
    t = _THREADS[thread_id]
    return ThreadOut(
        id=t["id"],
        title=t["title"],
        created_at=t["created_at"],
        updated_at=t["updated_at"],
    )


@router.delete("/assistant/threads/{thread_id}")
def delete_thread(thread_id: str):
    if thread_id not in _THREADS:
        raise HTTPException(status_code=404, detail="Thread not found")
    del _THREADS[thread_id]
    return {"ok": True}


@router.get("/assistant/threads/{thread_id}/messages", response_model=List[MessageOut])
def list_messages(thread_id: str):
    if thread_id not in _THREADS:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _THREADS[thread_id]["messages"]


@router.post("/assistant/threads/{thread_id}/messages", response_model=MessageOut)
def add_message(thread_id: str, payload: MessageIn):
    if thread_id not in _THREADS:
        # auto-create if missing
        now = _now()
        _THREADS[thread_id] = {
            "id": thread_id,
            "title": "New chat",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }

    msg = MessageOut(
        id=str(uuid.uuid4()),
        created_at=_now(),
        role=payload.role,
        content=payload.content,
    )
    _THREADS[thread_id]["messages"].append(msg)
    _THREADS[thread_id]["updated_at"] = _now()

    # Assistant placeholder reply for now (until you connect OpenAI)
    if payload.role == "user":
        reply = MessageOut(
            id=str(uuid.uuid4()),
            created_at=_now(),
            role="assistant",
            content="Got it. (Assistant skeleton) Next: connect OpenAI + retrieval + tool-calling.",
        )
        _THREADS[thread_id]["messages"].append(reply)
        _THREADS[thread_id]["updated_at"] = _now()
        return reply

    return msg
