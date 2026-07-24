"""SQLite data-access layer for Spendly.

Provides:
    get_db()            — open a connection to expense_tracker.db (row_factory + FKs on)
    init_db()           — create tables (idempotent)
    seed_db()           — insert demo data for development (idempotent)
    get_user_by_email() — look up a user row by email
    get_user_by_id()     — look up a user row by primary key
    create_user()       — insert a new user, return its new id
    get_expenses_by_user() — all expenses for a user, most recent first
    get_category_totals()  — per-category spend totals for a user, highest first
"""

import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

# database/db.py -> parent is database/ -> parent of that is project root.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "expense_tracker.db")

CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    password_hash = generate_password_hash("demo123")
    cursor.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", password_hash),
    )
    user_id = cursor.lastrowid

    now = datetime.now()

    def day(n):
        # All days below are <= 28, so this is safe for every month.
        return now.replace(day=n).strftime("%Y-%m-%d")

    expenses = [
        (user_id, 12.50, "Food", day(2), "Groceries at local market"),
        (user_id, 45.00, "Transport", day(4), "Monthly bus pass"),
        (user_id, 89.99, "Bills", day(5), "Electricity bill"),
        (user_id, 25.00, "Health", day(9), "Pharmacy — cold medicine"),
        (user_id, 15.00, "Entertainment", day(12), "Movie tickets"),
        (user_id, 60.00, "Shopping", day(15), "New running shoes"),
        (user_id, 8.75, "Other", day(18), "Miscellaneous"),
        (user_id, 22.30, "Food", day(21), "Dinner with friends"),
    ]

    cursor.executemany(
        """
        INSERT INTO expenses (user_id, amount, category, date, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        expenses,
    )
    conn.commit()
    conn.close()


def get_user_by_email(email):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row


def get_expenses_by_user(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def get_category_totals(user_id):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def create_user(name, email, password_hash):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, password_hash),
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id
