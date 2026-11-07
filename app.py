import os, re, secrets, datetime
from flask import Flask, render_template, request, redirect, url_for, abort

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB per order
UPLOAD_DIR = os.path.join(app.root_path, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
SHOP_WHATSAPP = "254700000000"  # <-- your shop number, no "+"

def sel(name, label, opts, default=0, show_full_price=False, base=0):
    options = []
    for value, option_label, add in opts:
        option = {"v": value, "l": option_label, "add": add}
        if show_full_price:
            option["price"] = base + add
        options.append(option)
    return {"name": name, "label": label, "type": "select", "default": opts[default][0],
            "options": options, "show_full_price": show_full_price}
def txt(name, label, hint=""):
    return {"name": name, "label": label, "type": "text", "hint": hint}

# files: "required" | "optional" | "none"   price = per unit (KES), add-ons come from options
CATALOG = [
  {"id": "sticker", "group": "decor", "name": "Wall stickers", "blurb": "Custom-cut vinyl from your design or photo.",
   "base": 10, "unit": "piece", "files": "required",
   "fields": [sel("size", "Size", [("Mini", "Mini sticker", 0), ("Normal", "Normal size", 20)], show_full_price=True, base=10),
              sel("finish", "Finish", [("Matte", "Matte", 0), ("Gloss", "Gloss", 30)])]},
  {"id": "portrait", "group": "decor", "name": "Wall portraits", "blurb": "Your photo, printed and ready to hang.",
   "base": 300, "unit": "portrait", "files": "required",
   "fields": [sel("size", "Size", [("A4", "A4", 0), ("A3", "A3", 300)], show_full_price=True, base=300),
              sel("frame", "Frame", [("None", "No frame", 0), ("Black", "Black frame", 700), ("Wood", "Wood frame", 900)])]},
  {"id": "print", "group": "cafe", "name": "Document printing", "blurb": "Black & white or colour, single or double sided.",
   "base": 5, "unit": "page", "files": "required",
   "fields": [sel("paper", "Paper size", [("A4", "A4", 0), ("A3", "A3", 15)]),
              sel("color", "Colour", [("B&W", "Black & white", 0), ("Colour", "Colour", 15)]),
              sel("sides", "Sides", [("Single", "Single sided", 0), ("Double", "Double sided", 0)])]},
  {"id": "edit", "group": "cafe", "name": "Document editing", "blurb": "CVs, letters, forms and typing from handwritten notes.",
   "base": 200, "unit": "document", "files": "required",
   "fields": [sel("kind", "What do you need?", [("Typing", "Typing / retyping", 0), ("CV", "CV or cover letter", 300), ("Formatting", "Formatting & fixes", 100)])]},
  {"id": "scan", "group": "cafe", "name": "Scanning", "blurb": "Paper to PDF or image, sent straight to WhatsApp.",
   "base": 20, "unit": "page", "files": "none",
   "fields": [sel("format", "Send me", [("PDF", "One PDF", 0), ("JPG", "Separate images", 0)])]},
  {"id": "apply", "group": "cafe", "name": "Official applications", "blurb": "We fill in and submit applications for you.",
   "base": 300, "unit": "application", "files": "optional",
   "fields": [sel("agency", "Application type", [("KRA", "KRA PIN / returns", 0), ("eCitizen", "eCitizen service", 100), ("SHA", "SHA registration", 0), ("HELB", "HELB", 100), ("Other", "Something else", 100)]),
              txt("ref", "ID number used for the application", "Needed to start the application")]},
]
BY_ID = {s["id"]: s for s in CATALOG}

def min_price(service):
    svc = BY_ID[service]
    return svc["base"] + sum(
        min(option["add"] for option in field["options"])
        for field in svc["fields"]
        if field["type"] == "select"
    )

app.jinja_env.globals["min_price"] = min_price

STOCK = [
  {"id": "sticker-leaf", "service": "sticker", "title": "Monstera leaves", "description": "A leafy pattern for a fresh, calm room.", "category": "Nature", "image": "monstera-leaves.jpg"},
  {"id": "sticker-wildflower", "service": "sticker", "title": "Wildflower garden", "description": "A soft floral border for your wall.", "category": "Nature", "image": "wildflower-garden.jpg"},
  {"id": "sticker-mountain", "service": "sticker", "title": "Mountain sunrise", "description": "Layered peaks with a bright morning sun.", "category": "Nature", "image": "mountain-sunrise.jpg"},
  {"id": "sticker-dream-big", "service": "sticker", "title": "Dream big", "description": "A little reminder to aim high.", "category": "Quotes", "image": "dream-big.jpg"},
  {"id": "sticker-kindness", "service": "sticker", "title": "Choose kindness", "description": "A cheerful message for any room.", "category": "Quotes", "image": "choose-kindness.jpg"},
  {"id": "sticker-space", "service": "sticker", "title": "Little astronaut", "description": "Planets and stars for curious explorers.", "category": "Kids", "image": "little-astronaut.jpg"},
  {"id": "sticker-dino", "service": "sticker", "title": "Dino friends", "description": "Friendly dinosaurs for a playful space.", "category": "Kids", "image": "dino-friends.jpg"},
  {"id": "sticker-rainbow", "service": "sticker", "title": "Rainbow shapes", "description": "Simple arches in warm, happy colours.", "category": "Abstract", "image": "rainbow-shapes.jpg"},
  {"id": "portrait-family", "service": "portrait", "title": "Family moments", "description": "A warm portrait layout for favourite photos.", "category": "Family", "image": "family-moments.jpg"},
  {"id": "portrait-botanical", "service": "portrait", "title": "Botanical study", "description": "A clean botanical print for quiet corners.", "category": "Nature", "image": "botanical-study.jpg"},
  {"id": "portrait-sunrise", "service": "portrait", "title": "Golden sunrise", "description": "A peaceful landscape in golden light.", "category": "Abstract", "image": "golden-sunrise.jpg"},
  {"id": "portrait-stars", "service": "portrait", "title": "Night sky", "description": "A deep blue sky filled with tiny stars.", "category": "Kids", "image": "night-sky.jpg"},
]
BY_STOCK_ID = {item["id"]: item for item in STOCK}

PHONE_RE = re.compile(r"^(?:\+?254|0)(7|1)\d{8}$")
def normalize_phone(raw):
    p = re.sub(r"[\s\-]", "", raw or "")
    if not PHONE_RE.match(p): return None
    return "254" + p[-9:]

@app.route("/")
def index():
    return render_template("index.html", catalog=CATALOG)

@app.route("/gallery")
def gallery():
    service = request.args.get("service", "")
    selected_service = service if service in ("sticker", "portrait") else ""
    return render_template(
        "gallery.html",
        stock=STOCK,
        categories=sorted({item["category"] for item in STOCK}),
        catalog=BY_ID,
        selected_service=selected_service,
    )

@app.route("/checkout")
def checkout():
    selected = request.args.get("service", "")
    stock_item = BY_STOCK_ID.get(request.args.get("stock", ""))
    if stock_item:
        selected = stock_item["service"]
    else:
        selected = selected if selected in BY_ID else ""
    custom = request.args.get("custom") == "1"
    return render_template(
        "checkout.html",
        catalog=CATALOG,
        selected=selected,
        stock_item=stock_item,
        custom=custom,
    )

@app.route("/submit", methods=["POST"])
def submit():
    svc = BY_ID.get(request.form.get("service", ""))
    phone = normalize_phone(request.form.get("whatsapp"))
    if not svc or not phone: abort(400)
    stock_id = request.form.get("stock_id", "").strip()
    stock_item = BY_STOCK_ID.get(stock_id) if stock_id else None
    if stock_id and (not stock_item or stock_item["service"] != svc["id"]): abort(400)
    size_field = next((field for field in svc["fields"] if field["name"] == "size"), None)
    if size_field and request.form.get("f_size") not in {option["v"] for option in size_field["options"]}:
        abort(400)
    qty = max(1, min(int(request.form.get("qty", 1) or 1), 9999))
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if svc["files"] == "required" and not files and not stock_item: abort(400)

    ref = "PH-" + secrets.token_hex(3).upper()
    folder = os.path.join(UPLOAD_DIR, ref); os.makedirs(folder)
    lines = [f"Order {ref}", f"Service: {svc['name']}", f"Quantity: {qty}", f"WhatsApp: {phone}"]
    if stock_item:
        lines.append(f"Stock design: {stock_item['title']} ({stock_item['id']})")
    elif svc["id"] in ("sticker", "portrait"):
        lines.append("Custom design: uploaded")
    for fld in svc["fields"]:
        lines.append(f"{fld['label']}: {request.form.get('f_' + fld['name'], '')}")
    lines.append(f"Notes: {request.form.get('notes', '')}")
    for i, f in enumerate(files):
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", f.filename)[-80:]
        f.save(os.path.join(folder, f"{i + 1}_{safe}"))
    with open(os.path.join(folder, "order.txt"), "w") as fh: fh.write("\n".join(lines))
    # TODO: notify the shop (WhatsApp Cloud API, email, Telegram...) here.
    return redirect(url_for("success", ref=ref))

@app.route("/success")
def success():
    ref = request.args.get("ref", "")
    if not re.fullmatch(r"PH-[0-9A-F]{6}", ref): return redirect(url_for("index"))
    return render_template("success.html", ref=ref, shop=SHOP_WHATSAPP)

@app.errorhandler(413)
def too_big(e): return "Files are too large. Keep each order under 50 MB.", 413

if __name__ == "__main__":
    app.run(debug=True)
