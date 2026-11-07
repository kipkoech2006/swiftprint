import os
import re
import secrets
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Order


class UploadError(ValueError):
    pass


def _matches_signature(ext: str, head: bytes) -> bool:
    """Check the file's magic bytes so a renamed .exe/.html can't pass as an image."""
    if ext == "pdf":
        return head.startswith(b"%PDF-")
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in ("jpg", "jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == "docx":
        return head.startswith(b"PK\x03\x04")
    return False


def save_upload(file_storage):
    """Validate and save one upload. Returns (stored_name, original_name) or None if empty."""
    if not file_storage or not file_storage.filename:
        return None

    raw_name = file_storage.filename
    ext = os.path.splitext(raw_name)[1].lstrip(".").lower()
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        allowed = ", ".join(sorted(current_app.config["ALLOWED_EXTENSIONS"]))
        raise UploadError(f"File type not allowed. Allowed: {allowed}.")

    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if not _matches_signature(ext, head):
        raise UploadError(f"'{secure_filename(raw_name) or raw_name}' is not a valid .{ext} file.")

    original = secure_filename(raw_name) or f"upload.{ext}"
    stored = f"{uuid.uuid4().hex}.{ext}"  # never trust user-supplied names on disk

    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    file_storage.save(folder / stored)
    return stored, original


def delete_upload(stored_name):
    try:
        (Path(current_app.config["UPLOAD_FOLDER"]) / stored_name).unlink(missing_ok=True)
    except OSError:
        current_app.logger.exception("Upload deletion failed")


def normalize_phone(raw):
    """Return digits-only international number (Kenya-friendly) or None if invalid."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        digits = "254" + digits
    return digits if re.fullmatch(r"\d{10,15}", digits) else None


def new_reference():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters
    while True:
        ref = "CW-" + "".join(secrets.choice(alphabet) for _ in range(6))
        if not db.session.execute(db.select(Order.id).filter_by(reference=ref)).first():
            return ref
