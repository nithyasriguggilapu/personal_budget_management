"""SQLite persistence helpers for the budget application."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DATABASE = Path(__file__).resolve().parent / "instance" / "budget.db"


@contextmanager
def get_connection(database_path=None):
    path = Path(database_path or DEFAULT_DATABASE)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db(database_path=None):
    with get_connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                transaction_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_date
            ON transactions(transaction_date DESC, id DESC)
            """
        )


def insert_transaction(
    transaction_type,
    amount_cents,
    category,
    description,
    transaction_date,
    database_path=None,
):
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO transactions
                (type, amount_cents, category, description, transaction_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                transaction_type,
                amount_cents,
                category,
                description,
                transaction_date,
            ),
        )
        row = connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def fetch_transactions(database_path=None, limit=None):
    query = "SELECT * FROM transactions ORDER BY transaction_date DESC, id DESC"
    parameters = ()
    if limit is not None:
        query += " LIMIT ?"
        parameters = (limit,)
    with get_connection(database_path) as connection:
        return [
            dict(row)
            for row in connection.execute(query, parameters).fetchall()
        ]


def fetch_transaction(transaction_id, database_path=None):
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        return dict(row) if row else None


def delete_transaction(transaction_id, database_path=None):
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM transactions WHERE id = ?", (transaction_id,)
        )
        return cursor.rowcount > 0


def fetch_totals(database_path=None):
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount_cents END), 0)
                    AS income_cents,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount_cents END), 0)
                    AS expense_cents,
                COUNT(*) AS transaction_count
            FROM transactions
            """
        ).fetchone()
        return dict(row)


def fetch_expense_categories(database_path=None):
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT category, SUM(amount_cents) AS amount_cents
            FROM transactions
            WHERE type = 'expense'
            GROUP BY category
            ORDER BY amount_cents DESC, category ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def fetch_monthly_totals(database_path=None, months=6):
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                strftime('%Y-%m', transaction_date) AS month,
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount_cents END), 0)
                    AS income_cents,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount_cents END), 0)
                    AS expense_cents
            FROM transactions
            WHERE strftime('%Y-%m', transaction_date) >= strftime('%Y-%m', date('now', ?))
            GROUP BY month
            ORDER BY month
            """,
            (f"-{months - 1} months",),
        ).fetchall()
        return [dict(row) for row in rows]
