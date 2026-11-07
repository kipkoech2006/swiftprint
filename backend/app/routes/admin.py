from functools import wraps

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import Category, DisplayImage, STATUSES, Order, OrderItem
from ..utils import UploadError, delete_upload, save_upload

bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pw_hash = current_app.config["ADMIN_PASSWORD_HASH"]
        if pw_hash and check_password_hash(pw_hash, request.form.get("password", "")):
            session.clear()
            session["is_admin"] = True
            return redirect(url_for("admin.dashboard"))
        flash("Wrong password.", "error")
    return render_template("admin/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@bp.route("/")
@admin_required
def dashboard():
    status = request.args.get("status")
    query = db.select(Order).order_by(Order.created_at.desc())
    if status == "active":
        query = query.filter(Order.status != "dismissed")
    elif status in STATUSES:
        query = query.filter_by(status=status)
    elif status == "all":
        pass
    else:
        status = "active"
        query = query.filter(Order.status != "dismissed")
    page = db.paginate(query, per_page=20, error_out=False)
    order_count = db.session.scalar(db.select(db.func.count()).select_from(Order)) or 0
    return render_template(
        "admin/dashboard.html",
        page=page,
        statuses=STATUSES,
        current=status,
        order_count=order_count,
    )


@bp.route("/order/<int:order_id>")
@admin_required
def order_detail(order_id):
    order = db.get_or_404(Order, order_id)
    return render_template("admin/order_detail.html", order=order, statuses=STATUSES)


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
    flash("Order dismissed. It remains available in the Dismissed filter.", "ok")
    return redirect(url_for("admin.dashboard"))


@bp.route("/display", methods=["GET"])
@admin_required
def display_manager():
    categories = db.session.scalars(
        db.select(Category).order_by(Category.name)
    ).all()
    return render_template("admin/display.html", categories=categories)


@bp.route("/display/categories", methods=["POST"])
@admin_required
def add_category():
    name = request.form.get("name", "").strip()[:80]
    if not name:
        flash("Enter a category name.", "error")
        return redirect(url_for("admin.display_manager"))
    if db.session.scalar(
        db.select(Category.id).where(db.func.lower(Category.name) == name.lower())
    ):
        flash("That category already exists.", "error")
        return redirect(url_for("admin.display_manager"))

    db.session.add(Category(name=name))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("That category already exists.", "error")
    else:
        flash("Category added.", "ok")
    return redirect(url_for("admin.display_manager"))


@bp.route("/display/images", methods=["POST"])
@admin_required
def add_display_image():
    category = db.get_or_404(Category, request.form.get("category_id", type=int))
    uploaded = request.files.get("image")
    extension = uploaded.filename.rsplit(".", 1)[-1].lower() if uploaded and uploaded.filename else ""
    if extension not in {"jpg", "jpeg", "png", "webp"}:
        flash("Choose a JPG, PNG, or WEBP image.", "error")
        return redirect(url_for("admin.display_manager"))

    try:
        saved = save_upload(uploaded)
    except UploadError as error:
        flash(str(error), "error")
        return redirect(url_for("admin.display_manager"))
    if not saved:
        flash("Choose an image to upload.", "error")
        return redirect(url_for("admin.display_manager"))

    image = DisplayImage(
        category=category,
        file_path=saved[0],
        original_filename=saved[1],
        alt_text=request.form.get("alt_text", "").strip()[:160],
    )
    db.session.add(image)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        delete_upload(saved[0])
        current_app.logger.exception("Display image save failed")
        flash("Something went wrong saving the image. Please try again.", "error")
    else:
        flash("Display image added.", "ok")
    return redirect(url_for("admin.display_manager"))


@bp.route("/display/images/<int:image_id>/delete", methods=["POST"])
@admin_required
def delete_display_image(image_id):
    image = db.get_or_404(DisplayImage, image_id)
    file_path = image.file_path
    db.session.delete(image)
    db.session.commit()
    delete_upload(file_path)
    flash("Display image removed.", "ok")
    return redirect(url_for("admin.display_manager"))


@bp.route("/display/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def delete_category(category_id):
    category = db.get_or_404(Category, category_id)
    if category.images:
        flash("Remove this category's images before deleting it.", "error")
        return redirect(url_for("admin.display_manager"))
    db.session.delete(category)
    db.session.commit()
    flash("Category deleted.", "ok")
    return redirect(url_for("admin.display_manager"))


@bp.route("/files/<int:item_id>")
@admin_required
def download(item_id):
    item = db.get_or_404(OrderItem, item_id)
    if not item.file_path:
        abort(404)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        item.file_path,
        as_attachment=True,  # forces download; never rendered in-browser
        download_name=f"{item.order.reference}-{item.original_filename}",
    )
