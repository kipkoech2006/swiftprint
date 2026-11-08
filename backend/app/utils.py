import os
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, namedtuple
from pathlib import Path

from flask import current_app, request
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Order


class UploadError(ValueError):
    pass


SavedFile = namedtuple("SavedFile", "stored original size")

# ---- file-type checking by content (magic bytes), not just by name ------------------------
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # old .doc/.xls/.ppt
_ZIP = b"PK\x03\x04"                         # .docx/.xlsx/.pptx/.odt/.ods/.odp
_RTF = b"{\\rtf"


def _office_old(h):
    return h.startswith(_OLE) or h.startswith(_ZIP) or h.lstrip().startswith(_RTF)


def _zip(h):
    return h.startswith(_ZIP)


def _jpeg(h):
    return h.startswith(b"\xff\xd8\xff")


def _tiff(h):
    return h[:4] in (b"II*\x00", b"MM\x00*")


def _ftyp(h):
    return h[4:8] == b"ftyp"  # HEIC/HEIF (iPhone photos)


CHECKS = {
    "pdf": lambda h: b"%PDF-" in h[:1024],
    "doc": _office_old, "xls": _office_old, "ppt": _office_old,
    "docx": _zip, "xlsx": _zip, "pptx": _zip, "odt": _zip, "ods": _zip, "odp": _zip,
    "rtf": lambda h: h.lstrip().startswith(_RTF),
    "txt": lambda h: b"\x00" not in h, "csv": lambda h: b"\x00" not in h,
    "jpg": _jpeg, "jpeg": _jpeg,
    "png": lambda h: h.startswith(b"\x89PNG\r\n\x1a\n"),
    "gif": lambda h: h[:6] in (b"GIF87a", b"GIF89a"),
    "bmp": lambda h: h[:2] == b"BM",
    "tif": _tiff, "tiff": _tiff,
    "webp": lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP",
    "heic": _ftyp, "heif": _ftyp,
}


def _size(file_storage):
    stream = file_storage.stream
    pos = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(pos)
    return size


def save_upload(file_storage, allowed=None, max_bytes=None):
    """Validate and store one upload under a random name. Returns SavedFile, or None if empty."""
    if not file_storage or not file_storage.filename:
        return None

    raw = file_storage.filename
    ext = os.path.splitext(raw)[1].lstrip(".").lower()
    base = secure_filename(os.path.splitext(raw)[0]) or "file"
    shown = f"{base}.{ext}" if ext else base

    allowed = allowed or current_app.config["ALLOWED_EXTENSIONS"]
    if ext not in allowed or ext not in CHECKS:
        raise UploadError(f"'{shown}' is not a supported file type.")

    size = _size(file_storage)
    if size == 0:
        raise UploadError(f"'{shown}' is empty.")
    limit = max_bytes or current_app.config["MAX_FILE_MB"] * 1024 * 1024
    if size > limit:
        raise UploadError(f"'{shown}' is bigger than {limit // (1024 * 1024)} MB.")

    file_storage.stream.seek(0)
    head = file_storage.stream.read(2048)
    file_storage.stream.seek(0)
    if not CHECKS[ext](head):
        raise UploadError(f"'{shown}' is not a genuine .{ext} file.")

    stored = f"{uuid.uuid4().hex}.{ext}"  # never trust user-supplied names on disk
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    file_storage.save(folder / stored)
    return SavedFile(stored, shown, size)


def delete_upload(stored_name):
    if not stored_name:
        return
    try:
        (Path(current_app.config["UPLOAD_FOLDER"]) / stored_name).unlink(missing_ok=True)
    except OSError:
        current_app.logger.exception("Upload deletion failed")


def human_size(num):
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024


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
    while True:
        ref = "PH-" + secrets.token_hex(3).upper()
        if not db.session.execute(db.select(Order.id).filter_by(reference=ref)).first():
            return ref


# ---- tiny in-memory rate limiter (per server process; best-effort protection) -------------
def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()  # last hop = added by the host's proxy
    return request.remote_addr or "unknown"


class RateLimiter:
    def __init__(self):
        self._hits = defaultdict(list)
        self._lock = threading.Lock()

    def _recent(self, key, window):
        cutoff = time.time() - window
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]
        return self._hits[key]

    def count(self, bucket, who, window):
        with self._lock:
            return len(self._recent((bucket, who), window))

    def hit(self, bucket, who, window):
        with self._lock:
            self._recent((bucket, who), window).append(time.time())

    def allow(self, bucket, who, limit, window):
        """Record an attempt; False when over the limit."""
        with self._lock:
            hits = self._recent((bucket, who), window)
            if len(hits) >= limit:
                return False
            hits.append(time.time())
            return True

    def reset(self, bucket, who):
        with self._lock:
            self._hits.pop((bucket, who), None)


limiter = RateLimiter()
