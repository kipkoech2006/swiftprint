import json
import re
import tempfile
import zipfile
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import (STATUS_LABELS, STATUSES, CatalogService, Category, DisplayImage, Order,
                      OrderFile, OrderItem)
from ..utils import UploadError, client_ip, delete_upload, limiter, save_upload

bp = Blueprint("admin", __name__)

LOGIN_LIMIT, LOGIN_WINDOW = 6, 900  # 6 wrong passwords per 15 minutes per connection


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


# ---------- login -------------------------------------------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("is_admin"):
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        ip = client_ip()
        if limiter.count("login", ip, LOGIN_WINDOW) >= LOGIN_LIMIT:
            flash("Too many wrong passwords. Wait 15 minutes and try again.", "error")
            return render_template("admin/login.html"), 429
        pw_hash = current_app.config["ADMIN_PASSWORD_HASH"]
        if pw_hash and check_password_hash(pw_hash, request.form.get("password", "")):
            limiter.reset("login", ip)
            session.clear()
            session["is_admin"] = True
            session.permanent = True
            return redirect(url_for("admin.dashboard"))
        limiter.hit("login", ip, LOGIN_WINDOW)
        if not pw_hash:
            flash("ADMIN_PASSWORD_HASH is not set in the .env file.", "error")
        else:
            flash("Wrong password.", "error")
    return render_template("admin/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You are logged out.", "ok")
    return redirect(url_for("admin.login"))


# ---------- orders ------------------------------------------------------------------------
@bp.route("/")
@admin_required
def dashboard():
    status = request.args.get("status", "active")
    q = request.args.get("q", "").strip()[:80]

    query = db.select(Order).order_by(Order.created_at.desc())
    if status == "all":
        pass
    elif status in STATUSES:
        query = query.where(Order.status == status)
    else:
        status = "active"
        query = query.where(Order.status != "dismissed")
    if q:
        conditions = [Order.reference.icontains(q, autoescape=True),
                      Order.customer_name.icontains(q, autoescape=True)]
        digits = re.sub(r"\D", "", q)
        if len(digits) >= 3:
            conditions.append(Order.whatsapp_number.contains(digits, autoescape=True))
        query = query.where(or_(*conditions))

    page = db.paginate(query, per_page=20, error_out=False)
    counts = dict(db.session.execute(db.select(Order.status, db.func.count()).group_by(Order.status)).all())
    total = sum(counts.values())
    return render_template(
        "admin/dashboard.html", page=page, statuses=STATUSES, labels=STATUS_LABELS, current=status,
        q=q, counts=counts, total=total, active_total=total - counts.get("dismissed", 0),
    )


def _status_message(order):
    shop = current_app.config["SHOP_NAME"]
    texts = {
        "new": f"Hello {order.customer_name}, we have received your order {order.reference} at {shop}. We will confirm the final price shortly.",
        "in_progress": f"Hello {order.customer_name}, we have started working on your order {order.reference}.",
        "ready": f"Hello {order.customer_name}, your order {order.reference} is ready. Payment is collected in person.",
        "collected": f"Hello {order.customer_name}, thank you for choosing {shop}! Order {order.reference} is complete.",
        "cancelled": f"Hello {order.customer_name}, your order {order.reference} was cancelled. Reply here if that is a mistake.",
    }
    return texts.get(order.status, f"Hello {order.customer_name}, about your order {order.reference}.")


@bp.route("/order/<int:order_id>")
@admin_required
def order_detail(order_id):
    order = db.get_or_404(Order, order_id)
    legacy = [i for i in order.items if i.file_path]
    return render_template(
        "admin/order_detail.html", order=order, statuses=STATUSES, labels=STATUS_LABELS, legacy=legacy,
        chat_link=f"https://wa.me/{order.whatsapp_number}",
        update_link=f"https://wa.me/{order.whatsapp_number}?text={quote(_status_message(order))}",
    )


@bp.route("/order/<int:order_id>/status", methods=["POST"])
@admin_required
def update_status(order_id):
    order = db.get_or_404(Order, order_id)
    new_status = request.form.get("status")
    if new_status in STATUSES:
        order.status = new_status
        db.session.commit()
        flash("Status updated.", "ok")
    return redirect(url_for("admin.order_detail", order_id=order.id))


@bp.route("/order/<int:order_id>/dismiss", methods=["POST"])
@admin_required
def dismiss_order(order_id):
    order = db.get_or_404(Order, order_id)
    order.status = "dismissed"
    db.session.commit()
    flash("Order dismissed. It stays available under the Dismissed tab.", "ok")
    return redirect(url_for("admin.dashboard"))


@bp.route("/order/<int:order_id>/delete", methods=["POST"])
@admin_required
def delete_order(order_id):
    order = db.get_or_404(Order, order_id)
    if order.status != "dismissed":
        flash("Dismiss the order before permanently deleting it.", "error")
        return redirect(url_for("admin.order_detail", order_id=order.id))
    stored = order.stored_file_names
    db.session.delete(order)
    db.session.commit()
    for name in stored:
        delete_upload(name)
    flash("Order and its files permanently deleted.", "ok")
    return redirect(url_for("admin.dashboard", status="dismissed"))


# ---------- customer files (admin only) ---------------------------------------------------
def _send(stored, download_name, inline=False):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], stored,
                               as_attachment=not inline, download_name=download_name)


@bp.route("/order-files/<int:file_id>")
@admin_required
def download_file(file_id):
    f = db.get_or_404(OrderFile, file_id)
    return _send(f.file_path, f"{f.order.reference}-{f.original_filename}")


@bp.route("/order-files/<int:file_id>/preview")
@admin_required
def preview_file(file_id):
    f = db.get_or_404(OrderFile, file_id)
    if not f.is_image:
        abort(404)
    return _send(f.file_path, f.original_filename, inline=True)


@bp.route("/files/<int:item_id>")  # legacy single-file orders
@admin_required
def download(item_id):
    item = db.get_or_404(OrderItem, item_id)
    if not item.file_path:
        abort(404)
    return _send(item.file_path, f"{item.order.reference}-{item.original_filename}")


@bp.route("/order/<int:order_id>/files.zip")
@admin_required
def download_zip(order_id):
    order = db.get_or_404(Order, order_id)
    entries = [(f.file_path, f.original_filename) for f in order.files]
    entries += [(i.file_path, i.original_filename or i.file_path) for i in order.items if i.file_path]
    if not entries:
        abort(404)
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    archive = tempfile.TemporaryFile()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as z:
        for n, (stored, original) in enumerate(entries, 1):
            path = folder / stored
            if path.is_file():
                z.write(path, arcname=f"{n:02d}-{original}")
    archive.seek(0)
    return send_file(archive, mimetype="application/zip", as_attachment=True,
                     download_name=f"{order.reference}-files.zip")


# ---------- designs (public gallery) ------------------------------------------------------
def _nice_title(filename):
    stem = re.sub(r"\.[^.]+$", "", filename)
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    return (stem[:1].upper() + stem[1:])[:120] if stem else "Design"


def _service_choices():
    return db.session.execute(
        db.select(CatalogService.id, CatalogService.name).order_by(CatalogService.name)).all()


@bp.route("/display", methods=["GET"])
@admin_required
def display_manager():
    categories = db.session.scalars(db.select(Category).order_by(Category.name)).all()
    drafts = db.session.scalar(
        db.select(db.func.count()).select_from(DisplayImage).where(DisplayImage.is_published.is_(False))) or 0
    return render_template("admin/display.html", categories=categories, drafts=drafts,
                           services=_service_choices())


@bp.route("/display/categories", methods=["POST"])
@admin_required
def add_category():
    name = request.form.get("name", "").strip()[:80]
    if not name:
        flash("Enter a category name.", "error")
    elif db.session.scalar(db.select(Category.id).where(db.func.lower(Category.name) == name.lower())):
        flash("That category already exists.", "error")
    else:
        db.session.add(Category(name=name))
        try:
            db.session.commit()
            flash(f"Category “{name}” added.", "ok")
        except IntegrityError:
            db.session.rollback()
            flash("That category already exists.", "error")
    return redirect(url_for("admin.display_manager"))


@bp.route("/display/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def delete_category(category_id):
    category = db.get_or_404(Category, category_id)
    if category.images:
        flash("Remove this category's designs before deleting it.", "error")
    else:
        db.session.delete(category)
        db.session.commit()
        flash("Category deleted.", "ok")
    return redirect(url_for("admin.display_manager"))


@bp.route("/display/images", methods=["POST"])
@admin_required
def add_display_image():
    # Category: pick an existing one, or type a new one on the spot.
    raw = request.form.get("category_id", "")
    category = None
    if raw == "new":
        name = request.form.get("new_category", "").strip()[:80]
        if not name:
            flash("Type a name for the new category.", "error")
            return redirect(url_for("admin.display_manager"))
        category = db.session.scalar(db.select(Category).where(db.func.lower(Category.name) == name.lower()))
        if not category:
            category = Category(name=name)
            db.session.add(category)
            db.session.flush()
    elif raw.isdigit():
        category = db.session.get(Category, int(raw))
    if not category:
        flash("Choose a category.", "error")
        return redirect(url_for("admin.display_manager"))

    uploads = [f for f in request.files.getlist("images") if f and f.filename]
    if not uploads:
        flash("Choose at least one photo to upload.", "error")
        db.session.rollback()
        return redirect(url_for("admin.display_manager"))

    valid_services = {row[0] for row in _service_choices()}
    service_id = request.form.get("service_id", "")
    service_id = service_id if service_id in valid_services else ""
    publish = request.form.get("publish") == "1"
    title_in = request.form.get("title", "").strip()[:120]
    description = request.form.get("description", "").strip()[:300]

    added, problems, stored_names = 0, [], []
    for upload in uploads[:40]:
        try:
            saved = save_upload(upload, allowed=current_app.config["ALLOWED_IMAGE_EXTENSIONS"])
        except UploadError as error:
            problems.append(str(error))
            continue
        stored_names.append(saved.stored)
        title = title_in if (len(uploads) == 1 and title_in) else _nice_title(saved.original)
        db.session.add(DisplayImage(
            category=category, file_path=saved.stored, original_filename=saved.original,
            alt_text=title, title=title, description=description, service_id=service_id,
            is_published=publish,
        ))
        added += 1
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        for name in stored_names:
            delete_upload(name)
        current_app.logger.exception("Design upload save failed")
        flash("Something went wrong saving the designs. Please try again.", "error")
        return redirect(url_for("admin.display_manager"))

    if added:
        flash(f"{added} design{'s' if added != 1 else ''} uploaded as "
              f"{'published' if publish else 'DRAFT. Review them below, then click Publish'}.", "ok")
    for problem in problems:
        flash(problem, "error")
    return redirect(url_for("admin.display_manager"))


@bp.route("/display/images/<int:image_id>/update", methods=["POST"])
@admin_required
def update_display_image(image_id):
    image = db.get_or_404(DisplayImage, image_id)
    title = request.form.get("title", "").strip()[:120]
    if not title:
        flash("A design needs a title.", "error")
        return redirect(url_for("admin.display_manager") + f"#d{image.id}")
    image.title = image.alt_text = title
    image.description = request.form.get("description", "").strip()[:300]
    category = db.session.get(Category, request.form.get("category_id", type=int) or 0)
    if category:
        image.category = category
    valid_services = {row[0] for row in _service_choices()}
    service_id = request.form.get("service_id", "")
    image.service_id = service_id if service_id in valid_services else ""
    db.session.commit()
    flash("Design updated.", "ok")
    return redirect(url_for("admin.display_manager") + f"#d{image.id}")


@bp.route("/display/images/<int:image_id>/publish", methods=["POST"])
@admin_required
def toggle_publish(image_id):
    image = db.get_or_404(DisplayImage, image_id)
    image.is_published = not image.is_published
    db.session.commit()
    flash("Published: customers can now see it." if image.is_published
          else "Hidden from customers (saved as draft).", "ok")
    return redirect(url_for("admin.display_manager") + f"#d{image.id}")


@bp.route("/display/publish-all", methods=["POST"])
@admin_required
def publish_all():
    drafts = db.session.scalars(db.select(DisplayImage).where(DisplayImage.is_published.is_(False))).all()
    for image in drafts:
        image.is_published = True
    db.session.commit()
    flash(f"Published {len(drafts)} draft design{'s' if len(drafts) != 1 else ''}.", "ok")
    return redirect(url_for("admin.display_manager"))


@bp.route("/display/images/<int:image_id>/delete", methods=["POST"])
@admin_required
def delete_display_image(image_id):
    image = db.get_or_404(DisplayImage, image_id)
    stored = image.file_path
    db.session.delete(image)
    db.session.commit()
    delete_upload(stored)
    flash("Design deleted.", "ok")
    return redirect(url_for("admin.display_manager"))


# ---------- services and prices -----------------------------------------------------------
@bp.route("/catalog", methods=["GET"])
@admin_required
def catalog_manager():
    services = db.session.scalars(
        db.select(CatalogService).order_by(CatalogService.group_name, CatalogService.name)).all()
    return render_template("admin/catalog.html", services=services)


def _validated_fields(raw):
    fields = json.loads(raw)
    if not isinstance(fields, list) or len(fields) > 20:
        raise ValueError("Specifications must be a JSON list with no more than 20 fields.")
    names = set()
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("Each specification must be a JSON object.")
        name, label = field.get("name"), field.get("label")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", name):
            raise ValueError("Specification names must use lowercase letters, digits, or underscores.")
        if name in names:
            raise ValueError("Specification names must be unique.")
        names.add(name)
        if not isinstance(label, str) or not label.strip() or len(label) > 100:
            raise ValueError("Each specification needs a label of at most 100 characters.")
        if field.get("type") == "text":
            field["hint"] = str(field.get("hint", ""))[:200]
            continue
        if field.get("type") != "select":
            raise ValueError("Specification type must be 'text' or 'select'.")
        options = field.get("options")
        if not isinstance(options, list) or not options or len(options) > 30:
            raise ValueError("Select specifications need between 1 and 30 options.")
        seen = set()
        for option in options:
            if not isinstance(option, dict):
                raise ValueError("Each select option must be a JSON object.")
            value, option_label, addition = option.get("v"), option.get("l"), option.get("add")
            if not isinstance(value, str) or not value or len(value) > 80 or value in seen:
                raise ValueError("Option values must be unique, non-empty strings up to 80 characters.")
            if not isinstance(option_label, str) or not option_label.strip() or len(option_label) > 120:
                raise ValueError("Each option needs a label of at most 120 characters.")
            if not isinstance(addition, int) or isinstance(addition, bool) or not 0 <= addition <= 1_000_000:
                raise ValueError("Option price additions must be whole numbers from 0 to 1,000,000.")
            seen.add(value)
        if field.get("default") not in seen:
            field["default"] = options[0]["v"]
        field["show_full_price"] = bool(field.get("show_full_price", False))
    return fields


def _read_service_form():
    name = request.form.get("name", "").strip()
    blurb = request.form.get("blurb", "").strip()
    unit = request.form.get("unit", "").strip()
    group_name = request.form.get("group_name", "")
    files = request.form.get("files", "")
    try:
        base_price = int(request.form.get("base_price", ""))
    except ValueError:
        raise ValueError("Base price must be a whole number.")
    if not name or len(name) > 100 or not unit or len(unit) > 40 or len(blurb) > 300:
        raise ValueError("Name, description, or unit is empty or too long.")
    if not 0 <= base_price <= 10_000_000:
        raise ValueError("Base price must be between 0 and 10,000,000 KES.")
    if group_name not in {"decor", "cafe"}:
        raise ValueError("Choose a valid service group.")
    if files not in {"required", "optional", "none"}:
        raise ValueError("Choose a valid file requirement.")
    fields = _validated_fields(request.form.get("fields_json", "[]") or "[]")
    return dict(name=name, blurb=blurb, unit=unit, group_name=group_name, files=files,
                base_price=base_price, fields=fields)


@bp.route("/catalog/new", methods=["POST"])
@admin_required
def add_catalog_service():
    try:
        data = _read_service_form()
    except (ValueError, json.JSONDecodeError) as error:
        flash(f"Service was not added: {error}", "error")
        return redirect(url_for("admin.catalog_manager"))
    slug = re.sub(r"[^a-z0-9]+", "-", data["name"].lower()).strip("-")[:24] or "service"
    service_id, n = slug, 2
    while db.session.get(CatalogService, service_id):
        service_id = f"{slug}-{n}"
        n += 1
    db.session.add(CatalogService(id=service_id, is_active=True, **data))
    db.session.commit()
    flash(f"Service “{data['name']}” added and visible on the website.", "ok")
    return redirect(url_for("admin.catalog_manager"))


@bp.route("/catalog/<string:service_id>", methods=["POST"])
@admin_required
def update_catalog_service(service_id):
    service = db.get_or_404(CatalogService, service_id)
    try:
        data = _read_service_form()
    except (ValueError, json.JSONDecodeError) as error:
        flash(f"Service was not saved: {error}", "error")
        return redirect(url_for("admin.catalog_manager"))
    for key, value in data.items():
        setattr(service, key, value)
    db.session.commit()
    flash("Service and pricing updated.", "ok")
    return redirect(url_for("admin.catalog_manager"))


@bp.route("/catalog/<string:service_id>/toggle", methods=["POST"])
@admin_required
def toggle_catalog_service(service_id):
    service = db.get_or_404(CatalogService, service_id)
    service.is_active = not service.is_active
    db.session.commit()
    flash("Service is now visible on the website." if service.is_active
          else "Service hidden from the website.", "ok")
    return redirect(url_for("admin.catalog_manager"))


@bp.route("/catalog/<string:service_id>/delete", methods=["POST"])
@admin_required
def delete_catalog_service(service_id):
    service = db.get_or_404(CatalogService, service_id)
    db.session.delete(service)
    db.session.commit()
    flash("Service deleted. Past orders keep their details.", "ok")
    return redirect(url_for("admin.catalog_manager"))
