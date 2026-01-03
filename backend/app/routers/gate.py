from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/v1/gate", tags=["gate"])


class GateCheckIn(BaseModel):
    password: str


class GateCheckOut(BaseModel):
    ok: bool
    token: str


def _get_gate_password() -> str:
    # Set SITE_GATE_PASSWORD in your backend environment (Render, Railway, etc.)
    return os.getenv("SITE_GATE_PASSWORD", "changeme")


def _get_jwt_secret() -> str:
    # Set the same GATE_JWT_SECRET in both backend and frontend environments.
    # This is used to sign/verify the gate token.
    secret = os.getenv("GATE_JWT_SECRET", "career-os")
    if not secret:
        raise RuntimeError("Missing GATE_JWT_SECRET env var")
    return secret


@router.post("/check", response_model=GateCheckOut)
def gate_check(payload: GateCheckIn):
    expected = _get_gate_password()
    if payload.password != expected:
        raise HTTPException(status_code=401, detail="Invalid password")

    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=7)

    token = jwt.encode(
        {"typ": "site_gate", "iat": int(now.timestamp()), "exp": int(exp.timestamp())},
        _get_jwt_secret(),
        algorithm="HS256",
    )

    return GateCheckOut(ok=True, token=token)
