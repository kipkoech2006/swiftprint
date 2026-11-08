from datetime import datetime, timezone

from .extensions import db

STATUSES = ["new", "in_progress", "ready", "collected", "cancelled", "dismissed"]

STATUS_LABELS = {
    "new": "New",
    "in_progress": "In progress",
    "ready": "Ready",
    "collected": "Completed",
    "cancelled": "Cancelled",
    "dismissed": "Dismissed",
}


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
    files = db.relationship(
        "OrderFile", back_populates="order", cascade="all, delete-orphan", order_by="OrderFile.id"
    )

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def stored_file_names(self):
        """Every file on disk that belongs to this order (new multi-file + legacy single file)."""
        names = [f.file_path for f in self.files]
        names += [i.file_path for i in self.items if i.file_path]
        return names

    @property
    def file_count(self):
        return len(self.stored_file_names)


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    item_type = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    specs = db.Column(db.JSON, default=dict)
    # Legacy single-file columns (orders placed before multi-file uploads). New orders use OrderFile.
    file_path = db.Column(db.String(255), nullable=True)
    original_filename = db.Column(db.String(255), nullable=True)

    order = db.relationship("Order", back_populates="items")


class OrderFile(db.Model):
    """One uploaded customer file (a document or photo to print or edit)."""
    __tablename__ = "order_files"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    file_path = db.Column(db.String(255), nullable=False)       # random stored name
    original_filename = db.Column(db.String(255), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)

    order = db.relationship("Order", back_populates="files")

    @property
    def extension(self):
        return self.file_path.rsplit(".", 1)[-1].lower() if "." in self.file_path else ""

    @property
    def is_image(self):
        return self.extension in {"jpg", "jpeg", "png", "webp", "gif", "bmp"}


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

    images = db.relationship(
        "DisplayImage", back_populates="category", cascade="all, delete-orphan",
        order_by="DisplayImage.id.desc()",
    )


class DisplayImage(db.Model):
    """A design/photo uploaded by the admin. Hidden from customers until published."""
    __tablename__ = "display_images"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    file_path = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    alt_text = db.Column(db.String(160), nullable=False, default="")  # kept for older databases
    title = db.Column(db.String(120), nullable=False, default="")
    description = db.Column(db.String(300), nullable=False, default="")
    service_id = db.Column(db.String(32), nullable=False, default="")  # "" = any service
    is_published = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    category = db.relationship("Category", back_populates="images")

    @property
    def label(self):
        return self.title or self.alt_text or self.original_filename


class CatalogService(db.Model):
    __tablename__ = "catalog_services"

    id = db.Column(db.String(32), primary_key=True)
    group_name = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    blurb = db.Column(db.String(300), nullable=False, default="")
    base_price = db.Column(db.Integer, nullable=False, default=0)
    unit = db.Column(db.String(40), nullable=False, default="item")
    files = db.Column(db.String(20), nullable=False, default="optional")
    fields = db.Column(db.JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
