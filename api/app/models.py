from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from .db import Base

class Admin(Base):
    __tablename__ = "admins"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)  # extension-provided user_id (V1)
    admin_id = Column(String, ForeignKey("admins.id"), nullable=True, index=True)
    name = Column(String, nullable=True)


class AuthCredential(Base):
    __tablename__ = "auth_credentials"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    principal_type = Column(String, nullable=False)  # 'admin' | 'user'
    principal_id = Column(String, nullable=False)    # admin_id or user_id
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, index=True, nullable=False)
    principal_type = Column(String, nullable=False)  # 'admin' | 'user'
    principal_id = Column(String, nullable=False)    # admin_id or user_id
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class BaseResume(Base):
    __tablename__ = "base_resumes"
    user_id = Column(String, primary_key=True)
    content_text = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    url = Column(String, index=True, nullable=False)
    stage = Column(String, default="applied")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class JobDescription(Base):
    __tablename__ = "job_descriptions"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    application_id = Column(Integer, index=True, nullable=False)
    jd_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class StoredFile(Base):
    __tablename__ = "stored_files"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    application_id = Column(Integer, index=True, nullable=False)
    kind = Column(String, nullable=False)  # resume_docx, cover_docx, resume_pdf...
    path = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
