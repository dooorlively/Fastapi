import sqlite3
import os

DB_PATH = "database.db"

# --- Удаляем старую базу для чистой инициализации ---
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# --- Таблица пользователей ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Добавляем админа, если его нет
cursor.execute("SELECT * FROM users WHERE username = ?", ('admin',))
if cursor.fetchone() is None:
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
        ('admin', '123', 'admin')
    )

# --- Таблица патронов ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caliber TEXT NOT NULL,
    ammo_type TEXT NOT NULL,
    designation TEXT NOT NULL,
    penetration INTEGER NOT NULL,
    fragmentation REAL NOT NULL,
    price REAL NOT NULL,
    image TEXT,
    description TEXT,
    availability_status TEXT DEFAULT 'in_stock',
    restock_hours INTEGER
)
''')

# --- Таблица бронежилетов ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS vests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    protection_level TEXT NOT NULL,
    weight REAL NOT NULL,
    price REAL NOT NULL,
    image TEXT,
    description TEXT,
    availability_status TEXT DEFAULT 'in_stock',
    restock_hours INTEGER
)
''')

# --- Таблица корзины ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS cart (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
)
''')

# --- Таблица заказов ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
''')

# --- Таблица элементов заказа ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER,   -- ссылка на патрон
    vest_id INTEGER,      -- ссылка на бронежилет
    quantity INTEGER NOT NULL,
    price_at_time REAL NOT NULL,
    item_type TEXT DEFAULT 'product',  -- "product" или "vest"
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (vest_id) REFERENCES vests(id)
)
''')

conn.commit()
conn.close()
print("База данных успешно инициализирована ✅")
