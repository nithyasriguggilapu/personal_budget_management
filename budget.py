"""Budget calculations and validation, kept separate from Flask routes."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import database


EXPENSE_CATEGORIES = (
    "Food",
    "Transportation",
    "Shopping",
    "Education",
    "Entertainment",
    "Healthcare",
    "Rent",
    "Other",
)
MAX_AMOUNT_CENTS = 99_999_999_999


class BudgetValidationError(ValueError):
    """Raised when a submitted budget transaction is invalid."""


def _required_text(value, label, max_length):
    if not isinstance(value, str) or not value.strip():
        raise BudgetValidationError(f"{label} is required.")
    value = value.strip()
    if len(value) > max_length:
        raise BudgetValidationError(f"{label} must be {max_length} characters or fewer.")
    return value


def _amount_in_cents(value):
    if isinstance(value, bool) or value is None:
        raise BudgetValidationError("Enter a valid amount greater than zero.")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise BudgetValidationError("Enter a valid amount greater than zero.") from None
    if not amount.is_finite() or amount <= 0:
        raise BudgetValidationError("Amount must be greater than zero.")
    if amount > Decimal(MAX_AMOUNT_CENTS) / 100:
        raise BudgetValidationError("Amount is too large.")
    try:
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise BudgetValidationError("Enter a valid amount.") from None
    cents = int(rounded * 100)
    if cents == 0:
        raise BudgetValidationError("Amount must be at least ₹0.01.")
    if cents > MAX_AMOUNT_CENTS:
        raise BudgetValidationError("Amount is too large.")
    return cents


def _transaction_date(value):
    if not isinstance(value, str) or not value.strip():
        raise BudgetValidationError("Date is required.")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise BudgetValidationError("Enter a valid date.") from None


def add_income(data, database_path=None):
    if not isinstance(data, dict):
        raise BudgetValidationError("Request data must be an object.")
    source = _required_text(data.get("source"), "Income source", 80)
    amount_cents = _amount_in_cents(data.get("amount"))
    transaction_date = _transaction_date(data.get("date"))
    return database.insert_transaction(
        "income",
        amount_cents,
        source,
        source,
        transaction_date,
        database_path,
    )


def add_expense(data, database_path=None):
    if not isinstance(data, dict):
        raise BudgetValidationError("Request data must be an object.")
    category = _required_text(data.get("category"), "Category", 40)
    if category not in EXPENSE_CATEGORIES:
        raise BudgetValidationError("Choose a valid expense category.")
    description = _required_text(data.get("description"), "Description", 200)
    amount_cents = _amount_in_cents(data.get("amount"))
    transaction_date = _transaction_date(data.get("date"))
    return database.insert_transaction(
        "expense",
        amount_cents,
        category,
        description,
        transaction_date,
        database_path,
    )


def _amount(cents):
    return round(cents / 100, 2)


def serialize_transaction(row):
    return {
        "id": row["id"],
        "type": row["type"],
        "amount": _amount(row["amount_cents"]),
        "category": row["category"],
        "description": row["description"],
        "date": row["transaction_date"],
    }


def get_summary(database_path=None):
    totals = database.fetch_totals(database_path)
    income = totals["income_cents"]
    expenses = totals["expense_cents"]
    return {
        "total_income": _amount(income),
        "total_expenses": _amount(expenses),
        "balance": _amount(income - expenses),
        "transaction_count": totals["transaction_count"],
    }


def get_category_summary(database_path=None):
    return [
        {"category": row["category"], "amount": _amount(row["amount_cents"])}
        for row in database.fetch_expense_categories(database_path)
    ]


def get_monthly_summary(database_path=None, months=6):
    rows = {
        row["month"]: row for row in database.fetch_monthly_totals(database_path, months)
    }
    today = date.today()
    result = []
    for offset in range(months - 1, -1, -1):
        month_index = today.year * 12 + today.month - 1 - offset
        year, month = divmod(month_index, 12)
        key = f"{year:04d}-{month + 1:02d}"
        row = rows.get(key, {})
        result.append(
            {
                "month": key,
                "income": _amount(row.get("income_cents", 0)),
                "expenses": _amount(row.get("expense_cents", 0)),
            }
        )
    return result
