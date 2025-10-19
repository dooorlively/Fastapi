import os
import re
import sqlite3
from typing import Optional
from PIL import Image

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from routes import auth, cart, products
from routes import vests
from database import get_db

# ----------------- Настройки -----------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="YOUR_SECRET_KEY")

DATABASE = "database.db"
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(auth.router)
app.include_router(cart.router)
app.include_router(products.router)
app.include_router(vests.router)


def url_for(request: Request, name: str, **path_params):
    return request.url_for(name, **path_params)


templates.env.globals['url_for'] = url_for


# ----------------- Хелперы -----------------


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
        raise HTTPException(status_code=401, detail="Not authenticated")


def admin_required(request: Request):
    if request.session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")


# ----------------- Роуты -----------------
@app.get("/", response_class=HTMLResponse, name="index")
async def index(request: Request):
    flash_msg = get_flash(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "flash": flash_msg,
        "session": request.session
    })


@app.get("/about", response_class=HTMLResponse, name="about")
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/register", response_class=HTMLResponse, name="register")
async def register_get(request: Request):
    flash_msg = get_flash(request)
    return templates.TemplateResponse("register.html", {"request": request, "flash": flash_msg})


@app.post("/register", name="register_post")
async def register_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, "user"))
    conn.commit()
    conn.close()
    flash(request, "Регистрация успешна")
    return RedirectResponse("/login", status_code=303)


@app.get("/login", response_class=HTMLResponse, name="login")
async def login_get(request: Request):
    flash_msg = get_flash(request)
    return templates.TemplateResponse("login.html", {"request": request, "flash": flash_msg})


@app.post("/login", name="login_post")
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


@app.get("/logout", name="logout")
async def logout(request: Request):
    request.session.pop("user", None)
    request.session.pop("role", None)
    request.session.pop("user_id", None)
    flash(request, "Вы вышли из системы")
    return RedirectResponse("/login", status_code=303)


@app.get("/add_product", response_class=HTMLResponse, name="add_product")
async def add_product_get(request: Request, _=Depends(admin_required)):
    flash_msg = get_flash(request)
    return templates.TemplateResponse("add_product.html", {"request": request, "flash": flash_msg})


@app.post("/add_product", name="add_product_post")
async def add_product_post(
        request: Request,
        caliber: str = Form(...),
        ammo_type: str = Form(...),
        designation: str = Form(...),
        penetration: int = Form(...),
        fragmentation: float = Form(...),
        price: float = Form(...),
        description: Optional[str] = Form(None),
        availability_status: Optional[str] = Form(None),
        restock_hours: Optional[int] = Form(None),
        image: Optional[UploadFile] = File(None),
        _=Depends(admin_required)
):
    image_filename = None
    if image and image.filename and allowed_file(image.filename):
        filename = secure_filename(image.filename)
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        contents = await image.read()
        with open(save_path, "wb") as f:
            f.write(contents)
        try:
            img = Image.open(save_path)
            img.thumbnail((300, 300))
            img.save(save_path)
        except Exception:
            pass
        image_filename = f"uploads/{filename}"

    conn = get_db()
    conn.execute('''
        INSERT INTO products (caliber, ammo_type, designation, penetration, fragmentation, price, image, description, availability_status, restock_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (caliber, ammo_type, designation, penetration, fragmentation, price, image_filename, description,
          availability_status, restock_hours))
    conn.commit()
    conn.close()

    flash(request, "Патрон добавлен")
    return RedirectResponse("/products", status_code=303)


@app.get("/products", response_class=HTMLResponse, name="products")
async def get_products(request: Request, caliber: str = "", ammo_type: str = ""):
    role = request.session.get("role", "user")  # <- важно передать роль
    conn = get_db()
    query = "SELECT * FROM products"
    params = []
    filters = []

    if caliber:
        filters.append("caliber LIKE ?")
        params.append(f"%{caliber}%")
    if ammo_type:
        filters.append("ammo_type LIKE ?")
        params.append(f"%{ammo_type}%")
    if filters:
        query += " WHERE " + " AND ".join(filters)

    items = conn.execute(query, params).fetchall()
    conn.close()

    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "items": items,
            "role": role  # <- передаём роль
        }
    )


@app.post("/delete_product/{product_id}", name="delete_product")
async def delete_product(product_id: int, request: Request, _=Depends(admin_required)):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    flash(request, "Товар удалён")
    return RedirectResponse("/products", status_code=303)


@app.post("/add_to_cart/{product_id}", name="add_to_cart")
async def add_to_cart(product_id: int, request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Требуется вход в аккаунт")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    existing = conn.execute("SELECT * FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id)).fetchone()
    if existing:
        conn.execute("UPDATE cart SET quantity = quantity + 1 WHERE id = ?", (existing["id"],))
    else:
        conn.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)", (user_id, product_id, 1))
    conn.commit()
    conn.close()
    flash(request, "Добавлено в корзину")
    return RedirectResponse("/cart", status_code=303)


@app.get("/cart", response_class=HTMLResponse, name="cart")
async def cart(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Войдите в аккаунт, чтобы просмотреть корзину")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    items = conn.execute('''
        SELECT cart.id AS cart_id, products.*, cart.quantity
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id = ?
    ''', (user_id,)).fetchall()
    conn.close()
    total = sum(item['price'] * item['quantity'] for item in items)
    flash_msg = get_flash(request)
    return templates.TemplateResponse("cart.html",
                                      {"request": request, "items": items, "total": total, "flash": flash_msg})


@app.post("/remove_from_cart/{cart_id}", name="remove_from_cart")
async def remove_from_cart(cart_id: int, request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Войдите в аккаунт")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    conn.execute("DELETE FROM cart WHERE id = ? AND user_id = ?", (cart_id, user_id))
    conn.commit()
    conn.close()
    flash(request, "Товар удалён из корзины")
    return RedirectResponse("/cart", status_code=303)


@app.post("/update_cart/{cart_id}", name="update_cart")
async def update_cart(cart_id: int, request: Request, quantity: int = Form(...)):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Войдите в аккаунт")
        return RedirectResponse("/login", status_code=303)
    if quantity < 1:
        quantity = 1
    conn = get_db()
    item = conn.execute("SELECT quantity FROM cart WHERE id = ? AND user_id = ?", (cart_id, user_id)).fetchone()
    if not item:
        conn.close()
        flash(request, "Элемент корзины не найден")
        return RedirectResponse("/cart", status_code=303)
    conn.execute("UPDATE cart SET quantity = ? WHERE id = ? AND user_id = ?", (quantity, cart_id, user_id))
    conn.commit()
    conn.close()
    return RedirectResponse("/cart", status_code=303)


@app.post("/checkout", name="checkout")
async def checkout(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Ошибка пользователя")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO orders (user_id) VALUES (?)", (user_id,))
    order_id = cursor.lastrowid

    cursor.execute('''
        SELECT product_id, quantity, products.price
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE user_id = ?
    ''', (user_id,))
    items = cursor.fetchall()

    for item in items:
        cursor.execute('''
            INSERT INTO order_items (order_id, product_id, quantity, price_at_time)
            VALUES (?, ?, ?, ?)
        ''', (order_id, item['product_id'], item['quantity'], item['price']))

    cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash(request, "Заказ успешно оформлен!")
    return RedirectResponse("/orders", status_code=303)


@app.get("/orders", response_class=HTMLResponse, name="orders")
async def order_history(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Ошибка пользователя")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    cursor = conn.cursor()

    # Получаем все заказы пользователя
    cursor.execute("""
        SELECT id AS order_id, created_at
        FROM orders
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))
    orders = cursor.fetchall()

    orders_data = []

    for order in orders:
        order_id = order["order_id"]

        cursor.execute("""
            SELECT oi.quantity, oi.price_at_time, oi.item_type,
                   COALESCE(p.designation, v.model) AS name,
                   COALESCE(p.image, v.image) AS image
            FROM order_items oi
            LEFT JOIN products p ON oi.item_type = 'product' AND oi.product_id = p.id
            LEFT JOIN vests v ON oi.item_type = 'vest' AND oi.product_id = v.id
            WHERE oi.order_id = ?
        """, (order_id,))
        items = cursor.fetchall()

        safe_items = []
        total_price = 0.0

        for item in items:
            quantity = int(item["quantity"] or 0)
            price_at_time = float(item["price_at_time"] or 0.0)
            total_price += quantity * price_at_time
            safe_items.append({
                "quantity": quantity,
                "price_at_time": price_at_time,
                "item_type": item["item_type"],
                "name": item["name"] or "Неизвестно",
                "image": item["image"]
            })

        orders_data.append({
            "order_id": order_id,
            "created_at": order["created_at"],
            "items": safe_items,
            "total": total_price
        })


@app.get("/profile", response_class=HTMLResponse, name="profile")
async def profile(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Ошибка пользователя")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, role, created_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    flash_msg = get_flash(request)
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
            "flash": flash_msg,
            "session": request.session  # вот это нужно
        }
    )


@app.get("/add_vest", response_class=HTMLResponse, name="add_vest")
async def add_vest_get(request: Request, _=Depends(admin_required)):
    flash_msg = get_flash(request)
    return templates.TemplateResponse(
        "add_vest.html",
        {
            "request": request,
            "flash": flash_msg,
            "session": request.session
        }
    )


@app.post("/add_vest", name="add_vest_post")
async def add_vest_post(
        request: Request,
        model: str = Form(...),
        protection_level: str = Form(...),
        weight: float = Form(...),
        price: float = Form(...),
        description: str = Form(...),
        availability_status: str = Form(...),
        restock_hours: Optional[int] = Form(None),
        image: Optional[UploadFile] = File(None),
        _=Depends(admin_required)
):
    image_filename = None
    if image and image.filename and allowed_file(image.filename):
        filename = secure_filename(image.filename)
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        contents = await image.read()
        with open(save_path, "wb") as f:
            f.write(contents)
        image_filename = f"uploads/{filename}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO vests (model, protection_level, weight, price, image, description, availability_status, restock_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (model, protection_level, weight, price, image_filename, description, availability_status, restock_hours))
    conn.commit()
    conn.close()

    flash(request, "Бронежилет добавлен")
    return RedirectResponse("/vests", status_code=303)


@app.get("/vests", response_class=HTMLResponse, name="vests")
async def vests_list(request: Request):
    role = request.session.get("role", "user")  # получаем роль
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vests")
    items = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "vests.html",
        {
            "request": request,
            "vests": items,
            "role": role  # обязательно передаём в шаблон
        }
    )


@app.post("/delete_vest/{vest_id}")
async def delete_vest(vest_id: int, request: Request):
    role = request.session.get("role") if request.session else None
    if role != "admin":
        return RedirectResponse("/vests", status_code=303)

    conn = get_db()
    conn.execute("DELETE FROM vests WHERE id = ?", (vest_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/vests", status_code=303)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    return templates.TemplateResponse("403.html", {"request": request}, status_code=403)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


# ----------------- Корзина и заказы для бронежилетов -----------------

@app.post("/add_vest_to_cart/{vest_id}", name="add_vest_to_cart")
async def add_vest_to_cart(vest_id: int, request: Request):
    """Добавляем бронежилет в сессию-корзину"""
    cart = request.session.get("cart_vests", [])
    if vest_id not in cart:
        cart.append(vest_id)
    request.session["cart_vests"] = cart
    flash(request, "Бронежилет добавлен в корзину ✅")
    return RedirectResponse("/cart_vests", status_code=303)


@app.get("/cart_vests", response_class=HTMLResponse, name="cart_vests")
async def cart_vests(request: Request):
    """Показываем корзину бронежилетов"""
    cart = request.session.get("cart_vests", [])
    items = []
    if cart:
        conn = get_db()
        placeholders = ",".join(["?"] * len(cart))
        query = f"SELECT id, model, protection_level, weight, price, image FROM vests WHERE id IN ({placeholders})"
        items = conn.execute(query, cart).fetchall()
        conn.close()
    flash_msg = get_flash(request)
    return templates.TemplateResponse("cart_vests.html", {
        "request": request,
        "items": items,
        "flash": flash_msg
    })


@app.post("/remove_vest_from_cart/{vest_id}", name="remove_vest_from_cart")
async def remove_vest_from_cart(vest_id: int, request: Request):
    """Удаляем бронежилет из корзины"""
    cart = request.session.get("cart_vests", [])
    cart = [v for v in cart if v != vest_id]
    request.session["cart_vests"] = cart
    flash(request, "Бронежилет удалён из корзины ✅")
    return RedirectResponse("/cart_vests", status_code=303)


@app.post("/checkout_vests", name="checkout_vests")
async def checkout_vests(request: Request):
    """Оформление заказа для бронежилетов"""
    user_id = get_current_user_id(request)
    cart = request.session.get("cart_vests", [])

    if not user_id:
        flash(request, "Ошибка пользователя")
        return RedirectResponse("/login", status_code=303)
    if not cart:
        flash(request, "Корзина пуста ❌")
        return RedirectResponse("/vests", status_code=303)

    conn = get_db()
    cursor = conn.cursor()

    # Создаём заказ
    cursor.execute("INSERT INTO orders (user_id, created_at) VALUES (?, datetime('now'))", (user_id,))
    order_id = cursor.lastrowid

    # Добавляем все бронежилеты из корзины в order_items
    placeholders = ",".join(["?"] * len(cart))
    query = f"SELECT id, price FROM vests WHERE id IN ({placeholders})"
    vests_in_cart = cursor.execute(query, cart).fetchall()

    for vest in vests_in_cart:
        cursor.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, price_at_time, item_type)
            VALUES (?, ?, ?, ?, ?)
        """, (order_id, vest["id"], 1, vest["price"], "vest"))

    conn.commit()
    conn.close()

    # Очистка корзины
    request.session["cart_vests"] = []
    flash(request, "✅ Заказ оформлен!")
    return RedirectResponse("/orders", status_code=303)
