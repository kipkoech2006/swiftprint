"""Starter services. Seeded ONLY on a brand-new database; afterwards manage them in the admin."""


def sel(name, label, opts, default=0, show_full_price=False):
    return {
        "name": name, "label": label, "type": "select", "default": opts[default][0],
        "options": [{"v": v, "l": l, "add": add} for v, l, add in opts],
        "show_full_price": show_full_price,
    }


def txt(name, label, hint=""):
    return {"name": name, "label": label, "type": "text", "hint": hint}


DEFAULT_CATALOG = [
    {"id": "sticker", "group": "decor", "name": "Wall stickers", "blurb": "Custom-cut vinyl from your design or photo.",
     "base": 10, "unit": "piece", "files": "required",
     "fields": [sel("size", "Size", [("Mini", "Mini sticker", 0), ("Normal", "Normal size", 20)], show_full_price=True),
                sel("finish", "Finish", [("Matte", "Matte", 0), ("Gloss", "Gloss", 30)])]},
    {"id": "portrait", "group": "decor", "name": "Wall portraits", "blurb": "Your photo, printed and ready to hang.",
     "base": 300, "unit": "portrait", "files": "required",
     "fields": [sel("size", "Size", [("A4", "A4", 0), ("A3", "A3", 300)], show_full_price=True),
                sel("frame", "Frame", [("None", "No frame", 0), ("Black", "Black frame", 700), ("Wood", "Wood frame", 900)])]},
    {"id": "print", "group": "cafe", "name": "Document printing", "blurb": "Black & white or colour, single or double sided.",
     "base": 5, "unit": "page", "files": "required",
     "fields": [sel("paper", "Paper size", [("A4", "A4", 0), ("A3", "A3", 15)]),
                sel("color", "Colour", [("B&W", "Black & white", 0), ("Colour", "Colour", 15)]),
                sel("sides", "Sides", [("Single", "Single sided", 0), ("Double", "Double sided", 0)])]},
    {"id": "edit", "group": "cafe", "name": "Document editing", "blurb": "Edit and print: CVs, letters, forms, typing from handwritten notes.",
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
