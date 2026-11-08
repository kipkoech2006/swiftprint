"""SwiftPrint: public website + admin. Entry point for `flask --app app ...` and PythonAnywhere."""
import click
from flask import Flask, jsonify, render_template, request, session
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash

from backend.config import Config
from backend.app.extensions import csrf, db
from backend.app import models  # noqa: F401  (registers tables)
from backend.app.models import Order
from backend.app.routes.admin import bp as admin_bp
from backend.app.routes.main import bp as main_bp
from backend.app.schema import drop_legacy_stock_table, ensure_schema, seed_catalog
from backend.app.utils import human_size

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config.from_object(Config)
if not app.config.get("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY is not set. Add it to the project-root .env file.")

db.init_app(app)
csrf.init_app(app)
app.register_blueprint(main_bp)
app.register_blueprint(admin_bp, url_prefix="/admin674")
app.jinja_env.filters["filesize"] = human_size

# Create / upgrade tables automatically whenever the app starts.
with app.app_context():
    try:
        ensure_schema()
        seed_catalog()
    except Exception:  # never stop the site from starting; the error log shows the details
        app.logger.exception("Startup database check failed")


@app.context_processor
def admin_context():
    if request.blueprint == "admin" and session.get("is_admin"):
        try:
            new_count = db.session.scalar(db.select(db.func.count()).select_from(Order).where(Order.status == "new")) or 0
        except Exception:
            new_count = 0
        return {"new_count": new_count}
    return {}


def _wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _error(code, title, message):
    if _wants_json():
        return jsonify(ok=False, errors=[message]), code
    return render_template("error.html", code=code, title=title, message=message), code


@app.errorhandler(CSRFError)
def csrf_error(_e):
    return _error(400, "Session expired",
                  "Your session expired or cookies are blocked. Reload the page and try again. "
                  "Make sure you are using the https:// address.")


@app.errorhandler(HTTPException)
def http_error(error):
    messages = {
        400: ("Bad request", "That request could not be processed."),
        403: ("Not allowed", "You do not have access to this page."),
        404: ("Page not found", "We could not find that page."),
        405: ("Not allowed", "That action is not allowed here."),
        413: ("Files too large", "Your files are too large. Send fewer or smaller files."),
        429: ("Slow down", "Too many requests. Please wait a moment and try again."),
    }
    title, message = messages.get(error.code, ("Something went wrong", "Please try again in a moment."))
    return _error(error.code or 500, title, message)


@app.errorhandler(Exception)
def unexpected_error(error):
    db.session.rollback()
    app.logger.exception("Unhandled error")
    return _error(500, "Something went wrong", "Something went wrong on our side. Please try again in a moment.")


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.cli.command("init-db")
def init_db():
    """Create/upgrade database tables and add starter services on a new database."""
    ensure_schema()
    added = seed_catalog()
    click.echo("Database is ready." + (" Starter services added." if added else ""))


@app.cli.command("remove-old-stock-designs")
def remove_old_stock_designs():
    """Delete the unused table that held the old built-in sample designs."""
    drop_legacy_stock_table()
    click.echo("Old sample-design table removed.")


@app.cli.command("hash-password")
@click.password_option()
def hash_password(password):
    """Print a password hash to set as ADMIN_PASSWORD_HASH in .env."""
    click.echo(generate_password_hash(password))


if __name__ == "__main__":
    app.run(debug=True)
