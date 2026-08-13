import os
import uuid

from app.config import settings


def save_upload(filename: str, data: bytes) -> str:
    """Dev-only local-volume storage standing in for S3. Returns the URL
    the file is served back at (see main.py's StaticFiles mount)."""
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1] or ""
    stored_name = f"{uuid.uuid4()}{ext}"
    path = os.path.join(settings.upload_dir, stored_name)

    with open(path, "wb") as f:
        f.write(data)

    return f"{settings.upload_base_url}/{stored_name}"
