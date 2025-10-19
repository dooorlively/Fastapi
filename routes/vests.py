from fastapi import APIRouter, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
import os
from dependencies import get_db, allowed_file, secure_filename, flash, get_flash, templates, get_current_user_id
import sqlite3

router = APIRouter()
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Зависимость для проверки админа ---
def admin_required(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")


# --- Добавление бронежилета (GET) ---
@router.get("/add_vest", response_class=HTMLResponse)
async def add_vest_get(request: Request, _=Depends(admin_required)):
    flash_msg = get_flash(request)
    return templates.TemplateResponse("add_vest.html", {"request": request, "flash": flash_msg})


# --- Добавление бронежилета (POST) ---
@router.post("/add_vest")
async def add_vest_post(
    request: Request,
    model: str = Form(...),
    protection_level: str = Form(...),
    weight: float = Form(...),
    price: float = Form(...),
    description: str = Form(...),
    availability_status: str = Form(...),
    restock_hours: int = Form(None),
    image: UploadFile = File(None),
    _=Depends(admin_required),
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
    cursor.execute(
        """
        INSERT INTO vests 
        (model, protection_level, weight, price, image, description, availability_status, restock_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (model, protection_level, weight, price, image_filename, description, availability_status, restock_hours),
    )
    conn.commit()
    conn.close()

    flash(request, "Бронежилет добавлен")
    return RedirectResponse("/vests", status_code=303)


# --- Список бронежилетов ---
@router.get("/vests", response_class=HTMLResponse)
async def get_vests(request: Request):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vests")
    rows = cursor.fetchall()
    conn.close()

    vests_list = [dict(row) for row in rows]
    flash_msg = get_flash(request)

    # Определяем роль пользователя
    user_id = get_current_user_id(request)
    role = "user"
    if user_id:
        conn = get_db()
        u = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        if u:
            role = u["role"]

    return templates.TemplateResponse(
        "vests.html", {"request": request, "vests": vests_list, "flash": flash_msg, "role": role}
    )


# --- Удаление бронежилета ---
@router.post("/delete_vest/{vest_id}")
async def delete_vest(vest_id: int, request: Request, _=Depends(admin_required)):
    conn = get_db()
    conn.execute("DELETE FROM vests WHERE id = ?", (vest_id,))
    conn.commit()
    conn.close()
    flash(request, "Бронежилет удалён")
    return RedirectResponse("/vests", status_code=303)


# --- Добавление в корзину бронежилетов ---
@router.post("/add_vest_to_cart/{vest_id}")
async def add_vest_to_cart(vest_id: int, request: Request):
    cart = request.session.get("cart_vests", [])
    cart.append(vest_id)
    request.session["cart_vests"] = cart
    flash(request, "Бронежилет добавлен в корзину ✅")
    return RedirectResponse("/cart_vests", status_code=303)


# --- Просмотр корзины бронежилетов ---
@router.get("/cart_vests", response_class=HTMLResponse)
async def cart_vests(request: Request):
    cart = request.session.get("cart_vests", [])
    items = []
    if cart:
        conn = get_db()
        query = f"SELECT id, model, protection_level, weight, price, image FROM vests WHERE id IN ({','.join(['?']*len(cart))})"
        rows = conn.execute(query, cart).fetchall()
        conn.close()
        items = [dict(row) for row in rows]

    flash_msg = get_flash(request)
    return templates.TemplateResponse("cart_vests.html", {
        "request": request,
        "items": items,
        "flash": flash_msg
    })


# --- Удаление из корзины бронежилетов ---
@router.post("/remove_vest_from_cart/{vest_id}")
async def remove_vest_from_cart(vest_id: int, request: Request):
    cart = request.session.get("cart_vests", [])
    cart = [v for v in cart if v != vest_id]
    request.session["cart_vests"] = cart
    flash(request, "Бронежилет удалён из корзины ✅")
    return RedirectResponse("/cart_vests", status_code=303)


# --- Оформление заказа бронежилетов ---
@router.post("/checkout_vests")
async def checkout_vests(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Ошибка пользователя")
        return RedirectResponse("/login", status_code=303)

    cart = request.session.get("cart_vests", [])
    if not cart:
        flash(request, "Корзина пуста ❌")
        return RedirectResponse("/vests", status_code=303)

    conn = get_db()
    cursor = conn.cursor()

    # Создаём заказ
    cursor.execute("INSERT INTO orders (user_id, created_at) VALUES (?, datetime('now'))", (user_id,))
    order_id = cursor.lastrowid

    # Добавляем бронежилеты в order_items
    for vest_id in cart:
        cursor.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, price_at_time, item_type)
            SELECT ?, id, 1, price, 'vest' FROM vests WHERE id = ?
        """, (order_id, vest_id))

    conn.commit()
    conn.close()

    # Очистка корзины
    request.session["cart_vests"] = []
    flash(request, "✅ Заказ оформлен!")
    return RedirectResponse("/orders", status_code=303)
