from urllib.parse import quote

from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   send_from_directory, url_for)

from ..extensions import db
from ..models import Category, DisplayImage, Order, OrderItem
from ..utils import UploadError, delete_upload, new_reference, normalize_phone, save_upload

bp = Blueprint("main", __name__)

ITEM_TYPES = ["Printing", "Photocopy / Scanning", "Photo print", "Portrait", "Wall decor", "Framing", "Other"]
MAX_ITEMS = 20


def _display_categories():
    return db.session.scalars(db.select(Category).order_by(Category.name)).all()


@bp.route("/", methods=["GET", "POST"])
def order_form():
    if request.method == "GET":
        return render_template(
            "order_form.html", item_types=ITEM_TYPES, categories=_display_categories()
        )

    name = request.form.get("customer_name", "").strip()[:120]
    phone = normalize_phone(request.form.get("whatsapp_number"))
    notes = request.form.get("notes", "").strip()[:2000]

    errors = []
    if not name:
        errors.append("Please enter your name.")
    if not phone:
        errors.append("Please enter a valid WhatsApp number, e.g. 0712 345 678.")

    # Item fields arrive as parallel lists (one entry per item row).
    types = request.form.getlist("item_type")[:MAX_ITEMS]
    qtys = request.form.getlist("item_quantity")
    sizes = request.form.getlist("item_size")
    finishes = request.form.getlist("item_finish")
    item_notes = request.form.getlist("item_notes")
    files = request.files.getlist("item_file")

    def at(lst, i, default=""):
        return lst[i].strip() if i < len(lst) and isinstance(lst[i], str) else default

    if not types:
        errors.append("Add at least one item.")

    saved_files = []
    items = []
    if not errors:
        try:
            for i, item_type in enumerate(types):
                if item_type not in ITEM_TYPES:
                    raise UploadError("Invalid item type.")
                try:
                    qty = max(1, min(int(at(qtys, i, "1")), 10000))
                except ValueError:
                    qty = 1
                saved = save_upload(files[i]) if i < len(files) else None
                if saved:
                    saved_files.append(saved[0])
                items.append(
                    OrderItem(
                        item_type=item_type,
                        quantity=qty,
                        specs={
                            "size": at(sizes, i)[:100],
                            "finish": at(finishes, i)[:100],
                            "notes": at(item_notes, i)[:1000],
                        },
                        file_path=saved[0] if saved else None,
                        original_filename=saved[1] if saved else None,
                    )
                )
        except UploadError as e:
            errors.append(str(e))

    if errors:
        for f in saved_files:
            delete_upload(f)
        for e in errors:
            flash(e, "error")
        return render_template(
            "order_form.html", item_types=ITEM_TYPES, categories=_display_categories()
        ), 400

    order = Order(reference=new_reference(), customer_name=name, whatsapp_number=phone, notes=notes, items=items)
    try:
        db.session.add(order)
        db.session.commit()
    except Exception:
        db.session.rollback()
        for f in saved_files:
            delete_upload(f)
        current_app.logger.exception("Order save failed")
        flash("Something went wrong saving your order. Please try again.", "error")
        return render_template(
            "order_form.html", item_types=ITEM_TYPES, categories=_display_categories()
        ), 500

    return redirect(url_for("main.success", reference=order.reference))


@bp.route("/display-images/<int:image_id>")
def display_image(image_id):
    image = db.get_or_404(DisplayImage, image_id)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"], image.file_path, conditional=True, max_age=3600
    )


@bp.route("/success/<reference>")
def success(reference):
    order = db.first_or_404(db.select(Order).filter_by(reference=reference))
    msg = f"Hello {current_app.config['SHOP_NAME']}, I just placed order {order.reference}. Please confirm."
    wa_link = None
    if current_app.config["SHOP_WHATSAPP"]:
        wa_link = f"https://wa.me/{current_app.config['SHOP_WHATSAPP']}?text={quote(msg)}"
    return render_template("success.html", order=order, wa_link=wa_link)
