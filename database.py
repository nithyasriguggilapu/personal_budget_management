"""SQLite persistence helpers for the budget application."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DATABASE = Path(__file__).resolve().parent / "instance" / "budget.db"


class DuplicateUserError(ValueError):
    """Raised when an email address or username is already registered."""


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
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
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
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(transactions)").fetchall()
        }
        if "user_id" not in columns:
            connection.execute(
                """
                ALTER TABLE transactions
                ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
                """
            )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_date
            ON transactions(transaction_date DESC, id DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_user_date
            ON transactions(user_id, transaction_date DESC, id DESC)
            """
        )


def create_user(full_name, email, username, password_hash, database_path=None):
    try:
        with get_connection(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (full_name, email, username, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (full_name, email, username, password_hash),
            )
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return dict(row)
    except sqlite3.IntegrityError as error:
        if "users.email" in str(error) or "users.username" in str(error):
            raise DuplicateUserError from None
        raise


def fetch_user_by_id(user_id, database_path=None):
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def fetch_user_by_identifier(identifier, database_path=None):
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT * FROM users
            WHERE email = ? COLLATE NOCASE OR username = ? COLLATE NOCASE
            """,
            (identifier, identifier),
        ).fetchone()
        return dict(row) if row else None


def insert_transaction(
    user_id,
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
                (type, amount_cents, category, description, transaction_date, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_type,
                amount_cents,
                category,
                description,
                transaction_date,
                user_id,
            ),
        )
        row = connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def fetch_transactions(user_id, database_path=None, limit=None):
    query = "SELECT * FROM transactions WHERE user_id = ? ORDER BY transaction_date DESC, id DESC"
    parameters = (user_id,)
    if limit is not None:
        query += " LIMIT ?"
        parameters = (user_id, limit)
    with get_connection(database_path) as connection:
        return [
            dict(row)
            for row in connection.execute(query, parameters).fetchall()
        ]


def fetch_transaction(transaction_id, user_id, database_path=None):
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def delete_transaction(transaction_id, user_id, database_path=None):
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, user_id),
        )
        return cursor.rowcount > 0


def fetch_totals(user_id, database_path=None):
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
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return dict(row)


def fetch_expense_categories(user_id, database_path=None):
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT category, SUM(amount_cents) AS amount_cents
            FROM transactions
            WHERE type = 'expense' AND user_id = ?
            GROUP BY category
            ORDER BY amount_cents DESC, category ASC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def fetch_monthly_totals(user_id, database_path=None, months=6):
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
            WHERE user_id = ?
                AND strftime('%Y-%m', transaction_date) >= strftime('%Y-%m', date('now', ?))
            GROUP BY month
            ORDER BY month
            """,
            (user_id, f"-{months - 1} months"),
        ).fetchall()
        return [dict(row) for row in rows]
