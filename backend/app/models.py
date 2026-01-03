from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from .db import Base


class Admin(Base):
    __tablename__ = "admins"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    dob = Column(String, nullable=True)  # ISO date string (YYYY-MM-DD)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)  # extension-provided user_id (V1)
    name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    dob = Column(String, nullable=True)  # ISO date string (YYYY-MM-DD)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AdminUser(Base):
    """Many-to-many link: a User can belong to many Admins and an Admin can manage many Users."""

    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True)
    admin_id = Column(String, ForeignKey("admins.id"), index=True, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("admin_id", "user_id", name="uq_admin_user"),)


class AuthCredential(Base):
    __tablename__ = "auth_credentials"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    principal_type = Column(String, nullable=False)  # 'admin' | 'user'
    principal_id = Column(String, nullable=False)  # admin_id or user_id
    principal_name = Column(String, nullable=False)  # principal name
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, index=True, nullable=False)
    principal_type = Column(String, nullable=False)  # 'admin' | 'user'
    principal_id = Column(String, nullable=False)  # admin_id or user_id
    principal_name = Column(String, nullable=False)  # principal name
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class BaseResume(Base):
    __tablename__ = "base_resumes"
    user_id = Column(String, primary_key=True)
    content_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Application(Base):
    __tablename__ = "applications"
    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    # "Workspace" admin context (who the user belongs to / which admin owns the pipeline).
    admin_id = Column(String, index=True, nullable=True)
    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    url = Column(String, index=True, nullable=False)
    source_site = Column(String, nullable=True)
    stage = Column(String, default="applied")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class JDKeyInfo(Base):
    __tablename__ = "jd_key_info"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    source_url = Column(String, index=True, nullable=True)
    url_hash = Column(String, index=True, nullable=True)
    text_hash = Column(String, index=True, nullable=False)
    scope = Column(String, default="fragment", nullable=False)  # canonical|fragment
    keys_json = Column(Text, nullable=False)
    model = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "url_hash",
            "scope",
            "text_hash",
            name="uq_jdkey_user_url_scope_text",
        ),
    )


class JobDescription(Base):
    __tablename__ = "job_descriptions"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    application_id = Column(String, index=True, nullable=False)
    jd_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StoredFile(Base):
    __tablename__ = "stored_files"
    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    application_id = Column(String, index=True, nullable=False)
    kind = Column(String, nullable=False)  # resume_docx, cover_docx, resume_pdf...
    path = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class OutlookIntegration(Base):
    __tablename__ = "outlook_integrations"
    user_id = Column(String, primary_key=True)
    account_email = Column(String, nullable=True)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    auto_update = Column(Integer, default=0)  # 0/1
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EmailEvent(Base):
    __tablename__ = "email_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    provider = Column(String, nullable=False, default="outlook")
    message_id = Column(String, nullable=False)  # Graph message id
    internet_message_id = Column(String, nullable=True)  # RFC 5322 Message-ID
    from_email = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    received_at = Column(DateTime, nullable=True)
    body_preview = Column(Text, nullable=True)
    web_link = Column(String, nullable=True)
    raw_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "internet_message_id",
            name="uq_email_user_provider_internetid",
        ),
    )


class ApplicationUpdateSuggestion(Base):
    __tablename__ = "application_update_suggestions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    application_id = Column(String, index=True, nullable=True)
    email_event_id = Column(Integer, ForeignKey("email_events.id"), nullable=False)
    suggested_stage = Column(String, nullable=False)
    confidence = Column(Integer, default=0)  # 0-100
    reason = Column(Text, nullable=True)
    status = Column(String, default="pending")  # pending|approved|rejected|applied
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
