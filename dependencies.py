import os
import re
import sqlite3
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

DATABASE = "database.db"
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def secure_filename(filename: str) -> str:
    filename = os.path.basename(filename)
    filename = filename.replace(" ", "_")
    filename = re.sub(r"[^A-Za-z0-9._-]", "", filename)
    return filename or "file"


# Flash messages stored in session["_flash"]
def flash(request: Request, message: str):
    request.session["_flash"] = message


def get_flash(request: Request) -> Optional[str]:
    return request.session.pop("_flash") if "_flash" in request.session else None


def get_current_user(request: Request) -> Optional[str]:
    return request.session.get("user")


def get_current_user_id(request: Request) -> Optional[int]:
    user = request.session.get("user")
    if not user:
        return None
    conn = get_db()
    u = conn.execute("SELECT id FROM users WHERE username = ?", (user,)).fetchone()
    conn.close()
    return u["id"] if u else None


def login_required(request: Request):
    if "user" not in request.session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def admin_required(request: Request):
    if request.session.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")