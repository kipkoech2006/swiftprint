import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")  # absolute path => works under PythonAnywhere too


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'shop.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads (requested location). Not publicly served: see before_request in app/__init__.py
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or str(BASE_DIR / "app" / "static" / "uploads")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024  # whole request
    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp", "docx"}

    # Admin + shop
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
    SHOP_WHATSAPP = os.environ.get("SHOP_WHATSAPP", "")
    SHOP_NAME = os.environ.get("SHOP_NAME", "Our Shop")

    # Cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"

    # Future payments (placeholders)
    MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "")
    MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "")
    MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "")
    MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY", "")
    MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL", "")
