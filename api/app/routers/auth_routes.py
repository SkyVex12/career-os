from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime
import secrets, hashlib, hmac, base64

from ..db import SessionLocal
from ..models import AuthCredential, AuthToken, Admin, User
from ..auth import get_principal, Principal

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- password hashing (stdlib-only) ---
def _hash_password(password: str, *, salt: bytes | None = None, iterations: int = 210_000) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return "pbkdf2_sha256$%d$%s$%s" % (
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(dk).decode("ascii").rstrip("="),
    )

def _verify_password(password: str, encoded: str) -> bool:
    try:
        algo, it_s, salt_s, hash_s = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(it_s)
        salt = base64.urlsafe_b64decode(salt_s + "==")
        expected = base64.urlsafe_b64decode(hash_s + "==")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False

def _issue_token(db: Session, principal_type: str, principal_id: str) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthToken(token=token, principal_type=principal_type, principal_id=principal_id, created_at=datetime.utcnow()))
    db.commit()
    return token

class SignupIn(BaseModel):
    email: str
    password: str = Field(..., min_length=6, max_length=128)
    account_type: str = Field(..., pattern="^(admin|user)$")
    # optional for user signup to attach to an admin
    admin_id: str | None = None
    user_id: str | None = None  # optional custom user id (else random)

class LoginIn(BaseModel):
    email: str
    password: str

@router.post("/auth/signup")
def signup(p: SignupIn, db: Session = Depends(get_db)):
    # prevent duplicate emails
    existing = db.query(AuthCredential).filter(AuthCredential.email == str(p.email)).first()
    if existing:
        raise HTTPException(400, "Email already registered")

    if p.account_type == "admin":
        admin_id = "a_" + secrets.token_hex(4)
        db.add(Admin(id=admin_id, name=str(p.email)))
        db.commit()
        principal_type, principal_id = "admin", admin_id
    else:
        user_id = (p.user_id or ("u_" + secrets.token_hex(4))).strip()
        # if admin_id provided, must exist
        if p.admin_id:
            a = db.query(Admin).filter(Admin.id == p.admin_id).first()
            if not a:
                raise HTTPException(400, "admin_id not found")
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            raise HTTPException(400, "user_id already exists")
        db.add(User(id=user_id, admin_id=p.admin_id, name=str(p.email)))
        db.commit()
        principal_type, principal_id = "user", user_id

    cred = AuthCredential(
        email=str(p.email),
        password_hash=_hash_password(p.password),
        principal_type=principal_type,
        principal_id=principal_id,
        created_at=datetime.utcnow(),
    )
    db.add(cred)
    db.commit()

    token = _issue_token(db, principal_type, principal_id)
    return {"ok": True, "token": token, "principal": {"type": principal_type, "id": principal_id}}

@router.post("/auth/login")
def login(p: LoginIn, db: Session = Depends(get_db)):
    cred = db.query(AuthCredential).filter(AuthCredential.email == str(p.email)).first()
    if not cred or not _verify_password(p.password, cred.password_hash):
        raise HTTPException(401, "Invalid email or password")

    token = _issue_token(db, cred.principal_type, cred.principal_id)
    return {"ok": True, "token": token, "principal": {"type": cred.principal_type, "id": cred.principal_id}}

@router.post("/auth/logout")
def logout(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    # revoke current token if present
    token = x_auth_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(400, "No token provided")
    db.query(AuthToken).filter(AuthToken.token == token).delete()
    db.commit()
    return {"ok": True}

@router.get("/me")
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    if principal["type"] == "admin":
        return {"type": "admin", "admin_id": principal["admin_id"]}
    return {"type": "user", "user_id": principal["user_id"]}
