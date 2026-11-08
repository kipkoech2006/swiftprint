import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
load_dotenv(PROJECT_DIR / ".env")


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'shop.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Private storage for customer files and design photos. Never served directly.
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or str(BASE_DIR / "app" / "static" / "uploads")

    # Size limits: whole request, one file, files per order.
    MAX_CONTENT_LENGTH = _int("MAX_UPLOAD_MB", 50) * 1024 * 1024
    MAX_FILE_MB = _int("MAX_FILE_MB", 25)
    MAX_FILES_PER_ORDER = _int("MAX_FILES_PER_ORDER", 10)

    # Everything a customer might want printed, or edited and then printed.
    ALLOWED_EXTENSIONS = {
        "pdf", "doc", "docx", "rtf", "txt", "odt",
        "xls", "xlsx", "csv", "ods",
        "ppt", "pptx", "odp",
        "jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp", "heic", "heif",
    }
    # Gallery/design photos shown on the website.
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

    # Admin + shop
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
    SHOP_WHATSAPP = "".join(ch for ch in os.environ.get("SHOP_WHATSAPP", "") if ch.isdigit())
    SHOP_NAME = os.environ.get("SHOP_NAME", "SwiftPrint")

    # Sessions / CSRF
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    WTF_CSRF_TIME_LIMIT = None  # a customer filling in a long form must not hit "expired token"
