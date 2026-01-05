# backend/app/storage.py
import os
import re
import cloudinary
import cloudinary.uploader


def safe_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_.-]+", "", s)
    return s[:80] or "file"


# Cloudinary config via env vars
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


def save_bytes(user_info: str, application_id: str, filename: str, data: bytes) -> str:
    """
    Upload file bytes to Cloudinary.
    Returns a secure URL that we store in DB.
    """
    filename = safe_filename(filename)

    result = cloudinary.uploader.upload(
        data,
        resource_type="raw",  # IMPORTANT for pdf/docx/etc
        type="upload",
        public_id=f"{user_info}/{application_id}/{filename}",
        overwrite=True,
    )

    return result["secure_url"]
