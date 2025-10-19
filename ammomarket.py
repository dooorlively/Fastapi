import asyncio
import os
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

# === Настройки ===
BOT_TOKEN = "8393290780:AAGvVaBExJkDT5GCA9UL5AbWT5VFtG_UIU8"
DB_PATH = "database.db"
STATIC_DIR = "static"  # папка с uploads

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Сессии пользователей: telegram_id -> user_id
user_sessions = {}

# ------------------- ХЕНДЛЕРЫ -------------------

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я бот магазина.\n"
        "Используйте:\n"
        " /login <имя> <пароль>\n"
        " /list — список товаров\n"
        " /profile — профиль\n"
        " /orders — история заказов"
    )


@dp.message(Command("login"))
async def login(message: types.Message):
    args = message.text.split()[1:]
    if len(args) != 2:
        await message.answer("Формат: /login <имя> <пароль>")
        return

    username, password = args

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = await cursor.fetchone()
        await cursor.close()

    if user:
        user_id, stored_password = user
        if password == stored_password:
            user_sessions[message.from_user.id] = user_id
            await message.answer(f"✅ Вход выполнен: {username}")
        else:
            await message.answer("❌ Неверный пароль")
    else:
        await message.answer("❌ Пользователь не найден")


@dp.message(Command("list"))
async def list_products(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, designation, caliber, ammo_type, price, availability_status, image FROM products"
        )
        rows = await cursor.fetchall()
        await cursor.close()

    if not rows:
        await message.answer("Нет товаров в базе.")
        return

    for pid, designation, caliber, ammo_type, price, availability, image in rows:
        status_text = {
            "in_stock": "✅ В наличии",
            "out_of_stock": "❌ Нет в наличии",
            "restocking": "⏳ Скоро будет"
        }.get(availability, "Неизвестно")

        caption = (
            f"<b>{designation}</b> ({caliber})\n"
            f"Тип: {ammo_type}\n"
            f"Цена: {price} грн\n"
            f"Статус: {status_text}"
        )

        if image:
            # путь к картинке внутри static/uploads
            photo_path = os.path.join(STATIC_DIR, image.replace("uploads/", "uploads/"))
            photo_path = os.path.abspath(photo_path)
            if os.path.exists(photo_path):
                await message.answer_photo(FSInputFile(photo_path), caption=caption, parse_mode="HTML")
            else:
                await message.answer(caption, parse_mode="HTML")
        else:
            await message.answer(caption, parse_mode="HTML")


@dp.message(Command("profile"))
async def profile(message: types.Message):
    telegram_id = message.from_user.id
    user_id = user_sessions.get(telegram_id)

    if not user_id:
        await message.answer("Сначала войдите с помощью /login")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT username, created_at, role FROM users WHERE id = ?", (user_id,))
        user = await cursor.fetchone()
        await cursor.close()

    if user:
        username, created_at, role = user
        await message.answer(
            f"<b>Профиль</b>\n"
            f"Имя: {username}\n"
            f"Роль: {role}\n"
            f"Дата регистрации: {created_at}",
            parse_mode="HTML"
        )
    else:
        await message.answer("Пользователь не найден")


@dp.message(Command("orders"))
async def orders(message: types.Message):
    telegram_id = message.from_user.id
    user_id = user_sessions.get(telegram_id)

    if not user_id:
        await message.answer("Сначала войдите с помощью /login")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
            (user_id,)
        )
        orders_list = await cursor.fetchall()
        await cursor.close()

    if not orders_list:
        await message.answer("У вас нет заказов.")
        return

    for order_id, created_at in orders_list:
        total_price = 0

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                SELECT oi.item_type, oi.quantity, oi.price_at_time,
                       p.designation, p.caliber, p.image AS p_image,
                       v.model, v.protection_level, v.image AS v_image
                FROM order_items oi
                LEFT JOIN products p ON oi.product_id = p.id
                LEFT JOIN vests v ON oi.vest_id = v.id
                WHERE oi.order_id = ?
                """,
                (order_id,)
            )
            items = await cursor.fetchall()
            await cursor.close()

        for item in items:
            item_type, quantity, price_at_time, designation, caliber, p_image, model, protection, v_image = item
            item_total = quantity * price_at_time
            total_price += item_total

            # Определяем, какой товар и картинку показывать
            if item_type == "vest" and model:
                caption = (
                    f"{model} (Уровень защиты: {protection})\n"
                    f"Кол-во: {quantity}\nЦена за шт: {price_at_time} грн\nИтого: {item_total} грн"
                )
                img_path = v_image
            elif item_type == "product" and designation:
                caption = (
                    f"{designation} ({caliber})\n"
                    f"Кол-во: {quantity}\nЦена за шт: {price_at_time} грн\nИтого: {item_total} грн"
                )
                img_path = p_image
            else:
                caption = f"Неизвестный товар\nКол-во: {quantity}\nЦена за шт: {price_at_time} грн\nИтого: {item_total} грн"
                img_path = None

            # Если есть картинка, показываем её
            if img_path:
                photo_path = os.path.join("static", img_path)  # static/uploads/...
                photo_path = os.path.abspath(photo_path)
                if os.path.exists(photo_path):
                    await message.answer_photo(FSInputFile(photo_path), caption=caption)
                else:
                    await message.answer(caption)
            else:
                await message.answer(caption)

        await message.answer(f"<b>Общая сумма заказа: {total_price} грн</b>", parse_mode="HTML")


# ------------------- Запуск -------------------

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
