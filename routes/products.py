from fastapi import APIRouter, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from PIL import Image
import os
from dependencies import get_db, allowed_file, secure_filename, flash, get_flash, templates, get_current_user, \
    get_current_user_id
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


@router.get("/add_product", response_class=HTMLResponse)
async def add_product_get(request: Request, _=Depends(admin_required)):
    flash_msg = get_flash(request)
    return templates.TemplateResponse("add_product.html", {"request": request, "flash": flash_msg})


@router.post("/add_product")
async def add_product_post(
        request: Request,
        caliber: str = Form(...),
        ammo_type: str = Form(...),
        designation: str = Form(...),
        penetration: int = Form(...),
        fragmentation: float = Form(...),
        price: float = Form(...),
        description: str = Form(None),
        availability_status: str = Form(None),
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
        try:
            img = Image.open(save_path)
            img.thumbnail((300, 300))
            img.save(save_path)
        except Exception:
            pass
        image_filename = f"uploads/{filename}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO products 
        (caliber, ammo_type, designation, penetration, fragmentation, price, image, description, availability_status, restock_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            caliber,
            ammo_type,
            designation,
            penetration,
            fragmentation,
            price,
            image_filename,
            description,
            availability_status,
            restock_hours,
        ),
    )
    conn.commit()
    conn.close()
    flash(request, "Патрон добавлен")
    return RedirectResponse("/products", status_code=303)


@router.get("/products", response_class=HTMLResponse)
async def get_products(request: Request, caliber: str = "", ammo_type: str = ""):
    conn = get_db()
    conn.row_factory = sqlite3.Row
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
    rows = conn.execute(query, params).fetchall()
    conn.close()

    products_list = [dict(row) for row in rows]
    flash_msg = get_flash(request)

    # Получаем роль для шаблона
    user_id = get_current_user_id(request)
    role = "user"
    if user_id:
        conn = get_db()
        u = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        if u:
            role = u["role"]

    return templates.TemplateResponse(
        "products.html",
        {"request": request, "items": products_list, "flash": flash_msg, "role": role},
    )


@router.post("/delete_product/{product_id}")
async def delete_product(product_id: int, request: Request, _=Depends(admin_required)):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    flash(request, "Товар удалён")
    return RedirectResponse("/products", status_code=303)
