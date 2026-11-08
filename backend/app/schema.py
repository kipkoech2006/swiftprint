"""Create tables, upgrade older databases in place, and seed the starter services.

Runs automatically when the app starts, so a forgotten `init-db` can't cause "no such table".
"""
from sqlalchemy import inspect, text

from .catalog_defaults import DEFAULT_CATALOG
from .extensions import db
from .models import CatalogService

# Columns added after the first release: table -> {column: DDL}. {T} becomes TRUE/1 per database.
NEW_COLUMNS = {
    "display_images": {
        "title": "VARCHAR(120) NOT NULL DEFAULT ''",
        "description": "VARCHAR(300) NOT NULL DEFAULT ''",
        "service_id": "VARCHAR(32) NOT NULL DEFAULT ''",
        "is_published": "BOOLEAN NOT NULL DEFAULT {T}",  # photos you already uploaded stay visible
        "created_at": "DATETIME",
    },
    "catalog_services": {
        "is_active": "BOOLEAN NOT NULL DEFAULT {T}",
    },
}


def ensure_schema():
    db.create_all()  # creates any missing tables (e.g. order_files)
    engine = db.engine
    true_value = "1" if engine.dialect.name == "sqlite" else "TRUE"
    inspector = inspect(engine)
    for table, columns in NEW_COLUMNS.items():
        if not inspector.has_table(table):
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name not in existing:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl.format(T=true_value)}"))
    db.session.commit()


def seed_catalog():
    """Add the starter services only when the catalog is completely empty (first install)."""
    if db.session.scalar(db.select(db.func.count()).select_from(CatalogService)):
        return False
    for s in DEFAULT_CATALOG:
        db.session.add(CatalogService(
            id=s["id"], group_name=s["group"], name=s["name"], blurb=s["blurb"],
            base_price=s["base"], unit=s["unit"], files=s["files"], fields=s["fields"],
        ))
    db.session.commit()
    return True


def drop_legacy_stock_table():
    """The old built-in stock designs table is no longer used. This removes it."""
    db.session.execute(text("DROP TABLE IF EXISTS stock_designs"))
    db.session.commit()
