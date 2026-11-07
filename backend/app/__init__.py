import click
from flask import Flask, abort, request
from werkzeug.security import generate_password_hash

from config import Config
from .extensions import csrf, db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Add it to your .env file.")

    db.init_app(app)
    csrf.init_app(app)

    from .routes.main import bp as main_bp
    from .routes.admin import bp as admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin674")

    @app.before_request
    def block_public_uploads():
        # Customer files must only be reachable through the authenticated admin route.
        if request.path.startswith("/static/uploads"):
            abort(404)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    @app.errorhandler(413)
    def too_large(_e):
        return "Upload too large. Please send smaller files.", 413

    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        click.echo("Database initialised.")

    @app.cli.command("hash-password")
    @click.password_option()
    def hash_password(password):
        """Print a hash to paste into ADMIN_PASSWORD_HASH."""
        click.echo(generate_password_hash(password))

    return app
