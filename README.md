# SwiftPrint: website, orders and admin

Customers browse designs, send files to print (or to edit and print), and get an order number. You manage everything from the admin page. **No online payment**: prices are estimates and payment is collected in person.

- Website: `https://YOURUSERNAME.pythonanywhere.com/`
- Admin: `https://YOURUSERNAME.pythonanywhere.com/admin674/` (note the trailing slash)

---

## 1. What I changed (exact list)

### 1.1 Why buttons were not clickable and uploads failed (root cause)
The old pages passed data to Alpine.js using `x-data="checkout({{ catalog|tojson }} ...)"`. Flask's `tojson` output contains double quotes, and the attribute itself was also wrapped in double quotes, so the browser cut the attribute at the first inner quote. Alpine then received broken JavaScript and **the whole component died**. That one bug caused all of these at once:

- gallery filter buttons did nothing
- the checkout page never showed the service choices or options
- the + / − quantity buttons and the file box did nothing, so orders could not be completed
- the site also depended on two outside CDNs (Tailwind and Alpine), so a slow connection could break it too

**Fix:** I removed Alpine and the Tailwind CDN completely. The site now uses one self-hosted stylesheet (`static/css/site.css`) and small plain JavaScript files. Filters, service choice and design choice are normal links that work even if JavaScript fails.

### 1.2 The website is empty until you upload
- Deleted all hard-coded sample designs/photos (the `DEFAULT_STOCK` list and the old built-in "stock designs" table is no longer read).
- The home page and Designs page show friendly empty states ("No designs yet") until you upload and **publish** designs in the admin.
- Services (stickers, portraits, printing, editing, scanning, applications) are not photos; they remain as starter services **only on a brand-new database**. You can edit, hide, delete or add services in the admin.

### 1.3 Designs: upload, review, then publish
- Upload **many photos at once** in **Admin → Designs**. New uploads are saved as **Draft** and customers cannot see them.
- Review each draft in the admin, edit its title, description, category and service, then click **Publish** (or **Publish all drafts**). You can **Hide from website** again at any time.
- You can create a category while uploading. Tick "Publish immediately" if you want to skip the review step.
- A draft's image address returns "not found" to the public, but you (logged in) can still see it.
- A customer clicks **Order this design** on a design and the order records which design they chose.

### 1.4 Uploads now accept anything that needs printing or editing
- Customers can send **several files in one order** (default up to 10, 25 MB each, 50 MB in total), by tapping or by drag and drop, with a list where each file can be removed, and an upload progress bar.
- Allowed types: PDF, Word (doc, docx, rtf, odt), text (txt), Excel (xls, xlsx, csv, ods), PowerPoint (ppt, pptx, odp), and images (jpg, jpeg, png, gif, bmp, tif, tiff, webp, heic, heif).
- Safety: every file is checked by its extension **and** by its real contents (a renamed `.exe` is rejected), saved under a random name, and is only downloadable by the logged-in admin.
- New table `order_files` stores each file (name, size). Old single-file orders still work and show "older order".

### 1.5 Every admin page is styled and mobile friendly
Login, Orders, Order detail, Designs and Services & prices all share one clean layout with a top menu, dark mode button and working buttons. The public pages the site redirects to (order success, track order, and error pages such as "Page not found", "Files too large" and "Session expired") are styled too.

### 1.6 Extra logic I added
- **Orders dashboard:** counts per status, search by name / order number / WhatsApp number, tabs per status, new-order badge in the menu.
- **Order detail:** download each file, **Download all (ZIP)**, inline previews for image files, one-click **WhatsApp** buttons, including a ready-made status message ("your order is ready…") that changes with the status.
- **Track my order:** customers enter their order number and WhatsApp number on `/track` to see progress (Received, In progress, Ready, Completed). Both must match.
- **Services admin:** add a new service, hide/show a service on the website, delete a service. Deleting a service does not bring it back when `init-db` runs again.
- **Friendly errors:** a bad form no longer shows a blank "400" page. Customers see what to fix and keep what they typed.
- **Protection:** admin login locks out after 6 wrong passwords in 15 minutes (per connection), a hidden anti-spam field and a limit of 15 orders per hour per connection, admin session expires after 8 hours, form tokens no longer expire while a customer fills in a long form.
- **Database upgrades are automatic:** when the site starts it creates missing tables and adds the new columns to your existing database. Photos you uploaded before are kept and stay visible (marked Published).

### 1.7 Files
**Added:** `README.md` (this file, replaces `backend/README.md`), `static/css/site.css`, `static/js/site.js`, `static/js/checkout.js`, `static/js/admin.js`, `templates/track.html`, `templates/error.html`, `templates/admin/` (base, login, dashboard, order_detail, display, catalog), `backend/app/schema.py`, `backend/app/catalog_defaults.py`.

**Rewritten:** `app.py` (now only sets up the app, error pages and commands), `backend/app/routes/main.py` (the public pages now live here), `backend/app/routes/admin.py`, `backend/app/models.py`, `backend/app/utils.py`, `backend/config.py`, `templates/base.html`, `index.html`, `gallery.html`, `checkout.html`, `success.html`, `.env.example`, `.gitignore`.

**Removed (they were duplicates or are no longer used):** `static/css/custom.css`, `static/js/theme.js`, `backend/app/templates/` (old unstyled pages), `backend/wsgi.py`, `backend/requirements.txt`, `backend/README.md`. The factory code inside `backend/app/__init__.py` was an unused second copy of the app, so that file is now empty.

**Unchanged:** the PythonAnywhere WSGI file (still `from app import app as application`), the admin address `/admin674/`, `requirements.txt` packages, your `.env`, your database and your uploaded files.

---

## 2. Using the admin

1. Log in at `/admin674/` with your admin password.
2. **Designs → Upload designs:** choose photos, pick or type a category, optionally pick the service (e.g. Wall portraits), click **Upload**. They appear below as **Draft**.
3. Check each one. Use **Edit details** if needed, then **Publish**. Open the website's Designs page to see how customers see it.
4. **Orders:** open an order to download files, message the customer on WhatsApp, and change the status. Use **Dismiss** when handled. A dismissed order can then be deleted permanently (this also deletes its files).
5. **Services & prices:** edit prices, add or hide services. The "Options" box is advanced JSON; leave it alone unless you need to change option names or extra prices.

---

## 3. Settings (`.env` file in the project root)

| Variable | Meaning |
|---|---|
| `SECRET_KEY` | Long random value. Required. |
| `ADMIN_PASSWORD_HASH` | The **hash** from `flask --app app hash-password` (never the plain password). |
| `SHOP_WHATSAPP` | Shop number, digits only with country code, e.g. `254712345678`. A phone number, not an API key. |
| `SHOP_NAME` | Name shown in the header and page titles. |
| `SESSION_COOKIE_SECURE` | `1` on PythonAnywhere (https). `0` only when testing locally on `http://127.0.0.1`. |
| `MAX_UPLOAD_MB` | Total size of one order's upload. Default 50. |
| `MAX_FILE_MB` | Size of one file. Default 25. **New.** |
| `MAX_FILES_PER_ORDER` | Files per order. Default 10. **New.** |
| `DATABASE_URL` | Leave empty to use SQLite (`backend/shop.db`). |

No payment, WhatsApp, email or SMS API keys are used.

---

## 4. What you must do when uploading this update to PythonAnywhere

Do these in order. Replace `YOURUSERNAME` with your username.

1. **Back up first.** In the **Files** tab download `swiftprint/backend/shop.db` and the folder `swiftprint/backend/app/static/uploads/`.
2. **Upload the new zip.** Files tab, open your home folder, **Upload a file** and choose the new zip (e.g. `swiftprint.zip`).
3. **Unpack over the old code** in a Bash console. This keeps your `.env`, database and uploads because the zip does not contain them:
   ```bash
   cd ~
   unzip -o swiftprint.zip -x "swiftprint/.git/*" -d ~
   ```
   (If you deploy with Git instead: push from your computer, then `cd ~/swiftprint && git pull`.)
4. **Delete the old leftovers** (optional but tidy):
   ```bash
   cd ~/swiftprint
   rm -rf backend/app/templates backend/wsgi.py backend/requirements.txt backend/README.md static/css/custom.css static/js/theme.js
   ```
5. **Update `.env`** (`nano ~/swiftprint/.env`). Make sure it has `SESSION_COOKIE_SECURE=1`, then add the new lines:
   ```
   MAX_FILE_MB=25
   MAX_FILES_PER_ORDER=10
   ```
   Keep your existing `SECRET_KEY`, `ADMIN_PASSWORD_HASH` and `SHOP_WHATSAPP`. Save with Ctrl+O, Enter, Ctrl+X.
6. **Install packages and upgrade the database:**
   ```bash
   workon swiftprint
   cd ~/swiftprint
   pip install -r requirements.txt
   flask --app app init-db
   flask --app app remove-old-stock-designs
   ```
   The second command removes the unused table that held the old sample designs. It is safe to skip.
7. **Web tab:**
   - WSGI file: nothing to change. Make sure its first line starts at the very left edge (no spaces).
   - If you added a **Static files** row (`/static/` → `/home/YOURUSERNAME/swiftprint/static`), keep it. **Never** map the uploads folder.
   - **Force HTTPS** must be enabled.
   - Click the green **Reload** button.
8. **Check it works** (also test on your phone):
   - Home page loads with colours and shows no designs.
   - Start an order: pick a service, press + and −, choose two or three files, send. You land on the success page with an order number.
   - Log in to `/admin674/`, open that order, download a file, try **Download all (ZIP)**.
   - Designs: upload a photo (Draft), confirm customers cannot see it, **Publish**, reload the public Designs page.

Your old orders and any photos you uploaded earlier are kept. Earlier photos stay visible (marked Published).

### Things that can bite
- Always open the site with **https://**. On plain http the security cookie is not sent, and login and uploads fail with "Session expired".
- Run `flask` commands from `~/swiftprint` (the folder with `app.py`), not from `backend/`.
- After any change to `.env` or code, press **Reload** on the Web tab.
- If you change `MAX_UPLOAD_MB` and large uploads still fail, check the Web tab error log.

---

## 5. Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # set SESSION_COOKIE_SECURE=0 for local http
python -c "import secrets; print(secrets.token_hex(32))"   # paste into SECRET_KEY
flask --app app hash-password                          # paste into ADMIN_PASSWORD_HASH
flask --app app init-db
flask --app app run --debug                            # http://127.0.0.1:5000  admin: /admin674/
```

## 6. Backups and housekeeping
- Back up `backend/shop.db` and `backend/app/static/uploads/` regularly (Files tab download).
- Delete handled orders (Dismiss, then Delete permanently) now and then to free disk space.

## 7. Known limits
- Customer files are not virus-scanned. They can only be downloaded by the admin; open unknown files with care.
- Login lockout and order limits are kept in memory per server process, so they are a best-effort guard rather than a hard limit.
- HEIC photos are accepted, but your computer must be able to open them.
- Google Fonts is the only outside resource used; the site falls back to system fonts if it cannot load.
