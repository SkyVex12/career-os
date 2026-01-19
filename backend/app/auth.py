from __future__ import annotations

from datetime import datetime
import secrets
from dataclasses import dataclass
from typing import Generator, Literal, Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import AuthToken


PrincipalType = Literal["user", "admin"]


@dataclass
class Principal:
    type: PrincipalType
    id: str  # user_id or admin_id
    name: Optional[str] = None


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _token_from_header(x_auth_token: Optional[str]) -> str:
    if not x_auth_token:
        raise HTTPException(status_code=401, detail="Missing X-Auth-Token")
    return x_auth_token.strip()


def get_principal(
    db: Session = Depends(get_db),
    x_auth_token: Optional[str] = Header(default=None, alias="X-Auth-Token"),
) -> Principal:
    token = _token_from_header(x_auth_token)

    row = db.query(AuthToken).filter(AuthToken.token == token).first()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid auth token")

    if row.principal_type not in ("user", "admin"):
        raise HTTPException(status_code=401, detail="Invalid token principal_type")

    return Principal(
        type=row.principal_type,
        id=row.principal_id,
        name=getattr(row, "principal_name", None),
    )


def require_admin(principal: Principal) -> Principal:
    if principal.type != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return principal


def require_user(principal: Principal) -> Principal:
    if principal.type != "user":
        raise HTTPException(status_code=403, detail="User required")
    return principal


def mint_token(
    db: Session,
    principal_type: PrincipalType,
    principal_id: str,
    principal_name: str | None = None,
) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            token=token,
            principal_type=principal_type,
            principal_id=principal_id,
            principal_name=principal_name,
            created_at=datetime.now(),
        )
    )
    return token
