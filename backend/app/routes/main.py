import json
import re
from urllib.parse import quote

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import (STATUS_LABELS, CatalogService, Category, DisplayImage, Order, OrderFile,
                      OrderItem)
from ..utils import (UploadError, client_ip, delete_upload, limiter, new_reference,
                     normalize_phone, save_upload)

bp = Blueprint("main", __name__)

REF_RE = re.compile(r"PH-[0-9A-F]{6}")
GROUPS = [("decor", "Wall decor", "Made to order from your photos and designs."),
          ("cafe", "Cyber cafe services", "Send your files and we print, or edit and print.")]


# ---------- helpers -----------------------------------------------------------------------
def service_dict(service):
    fields = json.loads(json.dumps(service.fields or []))
    min_add = 0
    for field in fields:
        if field.get("type") == "select":
            for option in field.get("options", []):
                option["price"] = service.base_price + option["add"]
            if field.get("options"):
                min_add += min(o["add"] for o in field["options"])
    return {
        "id": service.id, "group": service.group_name, "name": service.name,
        "blurb": service.blurb, "base": service.base_price, "unit": service.unit,
        "files": service.files, "fields": fields, "from_price": service.base_price + min_add,
    }


def active_services():
    rows = db.session.scalars(
        db.select(CatalogService).where(CatalogService.is_active.is_(True))
        .order_by(CatalogService.group_name, CatalogService.name)
    ).all()
    return [service_dict(s) for s in rows]


def published_designs():
    return db.select(DisplayImage).where(DisplayImage.is_published.is_(True)).order_by(DisplayImage.id.desc())


def _wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _whatsapp_link(message):
    shop = current_app.config["SHOP_WHATSAPP"]
    return f"https://wa.me/{shop}?text={quote(message)}" if shop else None


# ---------- public pages ------------------------------------------------------------------
@bp.route("/")
def index():
    services = active_services()
    designs = db.session.scalars(published_designs().limit(8)).all()
    return render_template("index.html", services=services, groups=GROUPS, designs=designs)


@bp.route("/gallery")
def gallery():
    services = {s["id"]: s for s in active_services()}
    service = request.args.get("service", "").strip()
    category_id = request.args.get("category", type=int)

    everything = db.session.scalars(published_designs()).all()
    categories = {}
    service_ids = []
    for d in everything:
        entry = categories.setdefault(d.category_id, {"id": d.category_id, "name": d.category.name, "count": 0})
        entry["count"] += 1
        if d.service_id and d.service_id in services and d.service_id not in service_ids:
            service_ids.append(d.service_id)

    query = published_designs()
    if service:
        query = query.where(DisplayImage.service_id == service)
    if category_id:
        query = query.where(DisplayImage.category_id == category_id)
    page = db.paginate(query, per_page=24, error_out=False)

    default_service = next((s["id"] for s in services.values() if s["group"] == "decor"), "")
    return render_template(
        "gallery.html", page=page, total_published=len(everything),
        categories=sorted(categories.values(), key=lambda c: c["name"].lower()),
        service_chips=[(sid, services[sid]["name"]) for sid in service_ids],
        services=services, service=service, category_id=category_id,
        default_service=default_service,
    )


@bp.route("/display-images/<int:image_id>")
def display_image(image_id):
    image = db.get_or_404(DisplayImage, image_id)
    if not image.is_published and not session.get("is_admin"):
        abort(404)  # drafts are visible to the admin only
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"], image.file_path, conditional=True,
        max_age=3600 if image.is_published else 0,
    )


def _render_checkout(service_id="", design_id=None, form=None, status=200):
    services = active_services()
    by_id = {s["id"]: s for s in services}
    design = None
    if design_id:
        found = db.session.get(DisplayImage, design_id)
        if found and found.is_published:
            design = found
            service_id = service_id or found.service_id or next(
                (s["id"] for s in services if s["group"] == "decor"), "")
    svc = by_id.get(service_id)
    allowed = sorted(current_app.config["ALLOWED_EXTENSIONS"])
    config = {
        "allowed": allowed,
        "maxFileMb": current_app.config["MAX_FILE_MB"],
        "maxFiles": current_app.config["MAX_FILES_PER_ORDER"],
        "filesRequired": bool(svc and svc["files"] == "required" and not design),
        "base": svc["base"] if svc else 0,
    }
    return render_template(
        "checkout.html", services=services, svc=svc, design=design, form=form or {},
        accept=",".join("." + e for e in allowed), cfg=config,
        max_files=config["maxFiles"], max_file_mb=config["maxFileMb"],
    ), status


@bp.route("/checkout")
def checkout():
    return _render_checkout(request.args.get("service", ""), request.args.get("design", type=int))


def _fail(errors, status=400):
    if _wants_json():
        return jsonify(ok=False, errors=errors), status
    for message in errors:
        flash(message, "error")
    return _render_checkout(
        request.form.get("service", ""), request.form.get("design_id", type=int),
        form=request.form, status=status,
    )


@bp.route("/submit", methods=["POST"])
def submit():
    if request.form.get("website"):  # honeypot: real people never fill this in
        return redirect(url_for("main.index"))

    ip = client_ip()
    if not limiter.allow("order", ip, 15, 3600):
        return _fail(["Too many orders from this connection. Please wait a while and try again."], 429)

    services = {s["id"]: s for s in active_services()}
    svc = services.get(request.form.get("service", ""))
    errors = []
    if not svc:
        errors.append("Choose a service.")

    name = request.form.get("customer_name", "").strip()[:120]
    if not name:
        errors.append("Enter your name.")
    phone = normalize_phone(request.form.get("whatsapp"))
    if not phone:
        errors.append("Enter a valid WhatsApp number, for example 0712 345 678.")

    design = None
    design_id = request.form.get("design_id", type=int)
    if design_id:
        design = db.session.get(DisplayImage, design_id)
        if design and not design.is_published:
            design = None

    field_values, option_add = {}, 0
    if svc:
        for field in svc["fields"]:
            value = request.form.get("f_" + field["name"], "").strip()[:500]
            if field["type"] == "select":
                option = next((o for o in field["options"] if o["v"] == value), None)
                if not option:
                    errors.append(f"Choose a valid option for “{field['label']}”.")
                    continue
                option_add += option["add"]
            field_values[field["name"]] = value

    try:
        qty = max(1, min(int(request.form.get("qty", 1) or 1), 9999))
    except ValueError:
        qty = 1

    uploads = [f for f in request.files.getlist("files") if f and f.filename]
    if svc and svc["files"] == "none":
        uploads = []
    max_files = current_app.config["MAX_FILES_PER_ORDER"]
    if len(uploads) > max_files:
        errors.append(f"You can send up to {max_files} files per order.")
    if svc and svc["files"] == "required" and not uploads and not design:
        errors.append("Please upload at least one file to print or edit.")

    saved = []
    if not errors:
        for upload in uploads:
            try:
                saved.append(save_upload(upload))
            except UploadError as error:
                errors.append(str(error))
    if errors:
        for s in saved:
            delete_upload(s.stored)
        return _fail(errors)

    unit_price = svc["base"] + option_add
    notes = request.form.get("notes", "").strip()[:2000]
    specs = {
        **field_values,
        "notes": notes,
        "design": design.label if design else "",
        "design_id": design.id if design else None,
        "estimated_unit_price": unit_price,
        "estimated_total": unit_price * qty,
    }
    order = Order(
        reference=new_reference(), customer_name=name, whatsapp_number=phone, notes=notes,
        items=[OrderItem(item_type=svc["name"], quantity=qty, specs=specs)],
        files=[OrderFile(file_path=s.stored, original_filename=s.original, size_bytes=s.size) for s in saved],
    )
    try:
        db.session.add(order)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        for s in saved:
            delete_upload(s.stored)
        current_app.logger.exception("Order save failed")
        return _fail(["Something went wrong saving your order. Please try again."], 500)

    target = url_for("main.success", ref=order.reference)
    return jsonify(ok=True, redirect=target) if _wants_json() else redirect(target)


@bp.route("/success")
def success():
    ref = request.args.get("ref", "")
    if not REF_RE.fullmatch(ref):
        return redirect(url_for("main.index"))
    order = db.first_or_404(db.select(Order).filter_by(reference=ref))
    link = _whatsapp_link(f"Hello, my order number is {order.reference}")
    return render_template("success.html", order=order, wa_link=link)


@bp.route("/track", methods=["GET", "POST"])
def track():
    order = None
    if request.method == "POST":
        ref = request.form.get("ref", "").strip().upper()
        phone = normalize_phone(request.form.get("whatsapp"))
        if not limiter.allow("track", client_ip(), 12, 900):
            flash("Too many tries. Please wait a few minutes and try again.", "error")
        else:
            if REF_RE.fullmatch(ref) and phone:
                order = db.session.scalar(
                    db.select(Order).filter_by(reference=ref, whatsapp_number=phone))
            if not order:
                flash("We could not find an order with that reference and WhatsApp number.", "error")
    steps = [("new", "Received"), ("in_progress", "In progress"), ("ready", "Ready"), ("collected", "Completed")]
    wa_link = _whatsapp_link(f"Hello, about my order {order.reference}") if order else None
    return render_template("track.html", order=order, steps=steps, wa_link=wa_link)
