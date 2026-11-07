from datetime import datetime, timezone

from .extensions import db

STATUSES = ["new", "in_progress", "ready", "collected", "cancelled", "dismissed"]


def _now():
    return datetime.now(timezone.utc)


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(16), unique=True, nullable=False, index=True)
    customer_name = db.Column(db.String(120), nullable=False)
    whatsapp_number = db.Column(db.String(20), nullable=False)  # digits only, e.g. 2547XXXXXXXX
    notes = db.Column(db.Text, default="")
    status = db.Column(db.String(20), nullable=False, default="new", index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, index=True)

    items = db.relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    item_type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    # Custom specifications, e.g. {"size": "A3", "finish": "matte", "notes": "..."}
    specs = db.Column(db.JSON, default=dict)
    # Stored (random) filename inside UPLOAD_FOLDER; original name kept for downloads.
    file_path = db.Column(db.String(255), nullable=True)
    original_filename = db.Column(db.String(255), nullable=True)

    order = db.relationship("Order", back_populates="items")


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

    images = db.relationship(
        "DisplayImage", back_populates="category", cascade="all, delete-orphan",
        order_by="DisplayImage.id.desc()",
    )


class DisplayImage(db.Model):
    __tablename__ = "display_images"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    file_path = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    alt_text = db.Column(db.String(160), nullable=False, default="")

    category = db.relationship("Category", back_populates="images")
