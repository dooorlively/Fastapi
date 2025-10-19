from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from dependencies import get_db, flash, get_flash, get_current_user_id, templates
import sqlite3

router = APIRouter()


@router.post("/add_to_cart/{product_id}")
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


@router.get("/cart", response_class=HTMLResponse)
async def cart(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Войдите в аккаунт, чтобы просмотреть корзину")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    items = conn.execute(
        """
        SELECT cart.id AS cart_id, products.*, cart.quantity
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    total = sum(item["price"] * item["quantity"] for item in items)
    flash_msg = get_flash(request)
    return templates.TemplateResponse("cart.html", {"request": request, "items": items, "total": total, "flash": flash_msg})


@router.post("/remove_from_cart/{cart_id}")
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


@router.post("/update_cart/{cart_id}")
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


@router.post("/checkout")
async def checkout(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Ошибка пользователя")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO orders (user_id) VALUES (?)", (user_id,))
    order_id = cursor.lastrowid

    cursor.execute(
        """
        SELECT product_id, quantity, products.price
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE user_id = ?
        """,
        (user_id,),
    )
    items = cursor.fetchall()

    for item in items:
        cursor.execute(
            """
            INSERT INTO order_items (order_id, product_id, quantity, price_at_time)
            VALUES (?, ?, ?, ?)
            """,
            (order_id, item["product_id"], item["quantity"], item["price"]),
        )

    cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash(request, "Заказ успешно оформлен!")
    return RedirectResponse("/orders", status_code=303)


@router.get("/orders", response_class=HTMLResponse)
async def order_history(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        flash(request, "Ошибка пользователя")
        return RedirectResponse("/login", status_code=303)

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Получаем заказы
    cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    orders_raw = cursor.fetchall()

    orders = []
    for order in orders_raw:
        cursor.execute("""
            SELECT oi.quantity, oi.price_at_time, oi.item_type,
                   COALESCE(p.designation, v.model) AS name,
                   COALESCE(p.image, v.image) AS image
            FROM order_items oi
            LEFT JOIN products p ON oi.item_type='product' AND oi.product_id=p.id
            LEFT JOIN vests v ON oi.item_type='vest' AND oi.product_id=v.id
            WHERE oi.order_id=?
        """, (order["id"],))
        items_raw = cursor.fetchall()

        items = []
        total = 0.0
        for item in items_raw:
            quantity = int(item["quantity"] or 0)
            price = float(item["price_at_time"] or 0)
            total += quantity * price
            items.append({
                "quantity": quantity,
                "price_at_time": price,
                "item_type": item["item_type"],
                "name": item["name"] or "Неизвестно",
                "image": item["image"]
            })

        orders.append({
            "order_id": order["id"],
            "created_at": order["created_at"],
            "items": items,
            "total": total
        })

    conn.close()
    flash_msg = get_flash(request)
    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders, "flash": flash_msg})
