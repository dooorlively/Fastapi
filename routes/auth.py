from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from dependencies import get_db, flash, get_flash, templates

router = APIRouter()


@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    flash_msg = get_flash(request)
    return templates.TemplateResponse("register.html", {"request": request, "flash": flash_msg})


@router.post("/register")
async def register_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, "user"))
    conn.commit()
    conn.close()
    flash(request, "Регистрация успешна")
    return RedirectResponse("/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    flash_msg = get_flash(request)
    return templates.TemplateResponse("login.html", {"request": request, "flash": flash_msg})


@router.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
    conn.close()
    if user:
        request.session["user"] = user["username"]
        request.session["user_id"] = user["id"]
        request.session["role"] = user["role"]
        flash(request, "Вход выполнен")
        return RedirectResponse("/", status_code=303)
    else:
        flash(request, "Неверные данные")
        return RedirectResponse("/login", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    request.session.pop("role", None)
    request.session.pop("user_id", None)
    flash(request, "Вы вышли из системы")
    return RedirectResponse("/login", status_code=303)