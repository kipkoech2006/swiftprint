# Cyber Cafe & Wall Decor Shop — Flask backend

Guest-only ordering (no customer accounts), secure uploads, WhatsApp confirmation, password-protected admin.
The website does not process payments. Payment is collected in person after delivery.

## Local setup
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then edit it
python -c "import secrets; print(secrets.token_hex(32))"   # paste into SECRET_KEY
flask --app wsgi hash-password                        # paste output into ADMIN_PASSWORD_HASH
flask --app wsgi init-db
flask --app wsgi run --debug                          # http://127.0.0.1:5000
```
Admin: http://127.0.0.1:5000/admin674/

## Admin features
- Sign in at `/admin674/` with the password configured as `ADMIN_PASSWORD_HASH`.
- The orders page shows the total number of orders, each customer's name and WhatsApp number, and links to the order details.
- Dismiss completed orders to remove them from the Active view. Dismissed orders remain stored and can be reopened from the Dismissed filter.
- Use **Manage display** to add categories and JPG, PNG, or WEBP photos. These categories and photos appear publicly on the order page. Customer order uploads remain private.
- After deploying this version to an existing installation, run `flask --app wsgi init-db` once to create the new display tables; existing orders are preserved.

## Where secrets live
Only in `.env` (never committed). `config.py` reads them.
On PythonAnywhere the `.env` file in the project folder is read the same way.

## Testing uploads
1. Submit the form with a real PNG/JPG/PDF/DOCX -> redirected to success page; file appears in `app/static/uploads/` with a random name.
2. Rename an `.exe` or `.html` to `.png` and upload -> rejected (magic-byte check).
3. Upload a `.exe`/`.html`/`.php` -> rejected (extension allowlist).
4. Upload > MAX_UPLOAD_MB -> HTTP 413.
5. Visit `/static/uploads/<stored-name>` -> 404. Customer order files are only downloadable by an admin; display photos are served through their public display-image URLs.
6. Log in at `/admin674/`, open an order, and click its file link -> downloads with the original name.

## Deploy on PythonAnywhere
1. Upload/clone the project to `/home/YOURUSERNAME/shop` (Files tab or `git clone` in a Bash console).
2. Bash console:
   ```bash
   cd ~/shop
   mkvirtualenv shopenv --python=python3.10     # pick a version matching your Web tab
   pip install -r requirements.txt
   cp .env.example .env && nano .env            # set SECRET_KEY, ADMIN_PASSWORD_HASH, SHOP_WHATSAPP, SESSION_COOKIE_SECURE=1
   flask --app wsgi init-db
   ```
3. Web tab -> Add a new web app -> Manual configuration -> same Python version.
4. Set **Virtualenv** to `/home/YOURUSERNAME/.virtualenvs/shopenv` and **Source code** to `/home/YOURUSERNAME/shop`.
5. Edit the WSGI file linked on the Web tab; replace its contents with:
   ```python
   import sys
   path = "/home/YOURUSERNAME/shop"
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import app as application
   ```
6. **Do not** add a Static files mapping for `/static/uploads`. Leave static mappings empty (Flask serves `/static`) so uploads stay private.
7. Click **Reload**. Visit `https://YOURUSERNAME.pythonanywhere.com/` and `/admin674/`.
8. After code or `.env` changes, click Reload. Errors: Web tab -> Error log.

## Notes
- Uploaded files and `shop.db` live on PythonAnywhere disk; back them up (Files tab download or a scheduled task).
- Free accounts restrict outbound internet to an allowlist (paid accounts are unrestricted).
- Next hardening steps: login rate limiting (Flask-Limiter), Flask-Migrate for schema changes, MySQL (PythonAnywhere offers it) via `DATABASE_URL`.
