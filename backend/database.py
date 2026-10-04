import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / 'data' / 'ledgerbite.db'
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys = ON')
    return c


def _add_column(c, table, column, definition):
    cols = {row['name'] for row in c.execute(f'PRAGMA table_info({table})').fetchall()}
    if column not in cols:
        c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')


def init_db():
    c = get_conn()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS receipts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor TEXT, receipt_date TEXT, total REAL, category TEXT,
        raw_text TEXT, location TEXT, user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS receipt_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id INTEGER NOT NULL,
        ingredient_name TEXT NOT NULL,
        quantity REAL DEFAULT 1,
        unit TEXT DEFAULT 'pcs',
        total_price REAL DEFAULT 0,
        unit_cost REAL DEFAULT 0,
        FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS ingredients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        quantity REAL DEFAULT 1,
        unit TEXT DEFAULT 'pcs',
        current_cost REAL DEFAULT 0,
        source TEXT DEFAULT 'manual',
        last_receipt_id INTEGER,
        last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(last_receipt_id) REFERENCES receipts(id) ON DELETE SET NULL,
        UNIQUE(user_id, name)
    );
    CREATE TABLE IF NOT EXISTS ingredient_price_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ingredient_id INTEGER NOT NULL,
        receipt_id INTEGER,
        cost REAL NOT NULL,
        unit TEXT NOT NULL,
        recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
        FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_date TEXT, description TEXT, amount REAL, category TEXT,
        location TEXT, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS cashouts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cash_date TEXT, cash_sales REAL, digital_sales REAL, other_sales REAL,
        cogs REAL, notes TEXT, location TEXT, user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(cash_date, location, user_id)
    );
    CREATE TABLE IF NOT EXISTS recipes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, selling_price REAL, location TEXT, user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS recipe_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER, ingredient_id INTEGER, ingredient_name TEXT,
        quantity REAL, unit TEXT, unit_cost REAL, source TEXT DEFAULT 'ingredient',
        FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
        FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL
    );
    ''')

    # Migrations for older Auth + CRUD databases.
    for table in ['receipts', 'expenses', 'cashouts', 'recipes']:
        _add_column(c, table, 'user_id', 'INTEGER')
    _add_column(c, 'recipe_items', 'ingredient_id', 'INTEGER')
    _add_column(c, 'recipe_items', 'source', "TEXT DEFAULT 'ingredient'")
    c.commit()
    c.close()
