"""Flask entry point for the Personal Budget Management System."""

import os
import re
import secrets
import tempfile
from datetime import timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash

import budget
import database


csrf = CSRFProtect()


def _load_secret_key(key_path):
    key_path = Path(key_path)
    try:
        secret_key = key_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".secret-key-", dir=key_path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
                secret_file.write(secrets.token_hex(32))
            try:
                os.link(temporary_path, key_path)
            except FileExistsError:
                pass
        finally:
            os.unlink(temporary_path)
        secret_key = key_path.read_text(encoding="utf-8").strip()

    if not secret_key:
        raise RuntimeError(
            "The local Flask secret key file is empty. Set the SECRET_KEY "
            "environment variable or replace the file."
        )
    return secret_key


def _login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("login", next=request.full_path))
        return view(**kwargs)

    return wrapped_view


def _safe_redirect_target(target):
    if not target:
        return None
    if "\\" in target or any(ord(character) < 32 for character in target):
        return None
    parts = urlsplit(target)
    if (
        parts.scheme
        or parts.netloc
        or not parts.path.startswith("/")
        or parts.path.startswith("//")
    ):
        return None
    return target


def _valid_email(value):
    return (
        isinstance(value, str)
        and len(value) <= 254
        and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is not None
    )


def _valid_password(value):
    return (
        isinstance(value, str)
        and 12 <= len(value) <= 128
        and any(char.islower() for char in value)
        and any(char.isupper() for char in value)
        and any(char.isdigit() for char in value)
        and any(not char.isalnum() for char in value)
    )


def create_app(test_config=None):
    app = Flask(__name__)
    secret_key = (
        os.environ.get("SECRET_KEY")
        or (test_config or {}).get("SECRET_KEY")
        or _load_secret_key(Path(app.instance_path) / ".secret_key")
    )
    app.config.from_mapping(
        DATABASE=str(Path(__file__).resolve().parent / "instance" / "budget.db"),
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    if test_config:
        app.config.update(test_config)
    csrf.init_app(app)
    database.init_db(app.config["DATABASE"])

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": generate_csrf}

    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        g.user = (
            database.fetch_user_by_id(user_id, app.config["DATABASE"])
            if user_id
            else None
        )
        if user_id and g.user is None:
            session.clear()

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        message = "Your form has expired or could not be verified. Please try again."
        if request.path.startswith("/api/"):
            return jsonify({"error": message}), 400
        return message, 400

    @app.get("/register")
    def register():
        if g.user is not None:
            return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.post("/register")
    def register_post():
        if g.user is not None:
            return redirect(url_for("dashboard"))
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or len(full_name) > 100:
            flash("Enter your full name (up to 100 characters).", "error")
        elif not _valid_email(email):
            flash("Enter a valid email address.", "error")
        elif re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username) is None:
            flash(
                "Username must be 3–30 characters using letters, numbers, dots, underscores, or hyphens.",
                "error",
            )
        elif not _valid_password(password):
            flash(
                "Use 12–128 characters with uppercase and lowercase letters, a number, and a symbol.",
                "error",
            )
        elif password != confirm_password:
            flash("Password and confirmation do not match.", "error")
        else:
            try:
                database.create_user(
                    full_name,
                    email,
                    username,
                    generate_password_hash(password),
                    app.config["DATABASE"],
                )
            except database.DuplicateUserError:
                flash("That email or username is already registered.", "error")
            else:
                flash("Your account is ready. Please log in.", "success")
                return redirect(url_for("login"))
        return render_template("register.html"), 400

    @app.get("/login")
    def login():
        if g.user is not None:
            return redirect(url_for("dashboard"))
        return render_template(
            "login.html", next_url=_safe_redirect_target(request.args.get("next"))
        )

    @app.post("/login")
    def login_post():
        if g.user is not None:
            return redirect(url_for("dashboard"))
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        user = database.fetch_user_by_identifier(identifier, app.config["DATABASE"])
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Email/username or password is incorrect.", "error")
            return render_template(
                "login.html",
                next_url=_safe_redirect_target(request.form.get("next")),
            ), 401

        session.clear()
        session["user_id"] = user["id"]
        session.permanent = request.form.get("remember_me") == "on"
        flash("Welcome back, {}.".format(user["full_name"]), "success")
        return redirect(
            _safe_redirect_target(request.form.get("next"))
            or url_for("dashboard")
        )

    @app.get("/forgot-password")
    def forgot_password():
        return render_template("forgot_password.html")

    @app.post("/logout")
    @_login_required
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.get("/")
    @_login_required
    def dashboard():
        return render_template("index.html", categories=budget.EXPENSE_CATEGORIES)

    @app.get("/transactions")
    @_login_required
    def transactions_page():
        return render_template("transactions.html")

    @app.get("/reports")
    @_login_required
    def reports_page():
        return render_template("reports.html")

    @app.get("/settings")
    @_login_required
    def settings_page():
        return render_template("settings.html")

    @app.get("/api/dashboard")
    @_login_required
    def dashboard_api():
        path = app.config["DATABASE"]
        user_id = g.user["id"]
        rows = database.fetch_transactions(user_id, path, limit=8)
        return jsonify(
            {
                "summary": budget.get_summary(user_id, path),
                "recent_transactions": [
                    budget.serialize_transaction(row) for row in rows
                ],
                "categories": budget.get_category_summary(user_id, path),
                "monthly": budget.get_monthly_summary(user_id, path),
            }
        )

    @app.post("/api/income")
    @_login_required
    def add_income_api():
        try:
            transaction = budget.add_income(
                request.get_json(silent=True), g.user["id"], app.config["DATABASE"]
            )
        except budget.BudgetValidationError as error:
            return jsonify({"error": str(error)}), 400
        return (
            jsonify(
                {
                    "message": "Income added successfully.",
                    "transaction": budget.serialize_transaction(transaction),
                }
            ),
            201,
        )

    @app.post("/api/expenses")
    @_login_required
    def add_expense_api():
        try:
            transaction = budget.add_expense(
                request.get_json(silent=True), g.user["id"], app.config["DATABASE"]
            )
        except budget.BudgetValidationError as error:
            return jsonify({"error": str(error)}), 400
        return (
            jsonify(
                {
                    "message": "Expense added successfully.",
                    "transaction": budget.serialize_transaction(transaction),
                }
            ),
            201,
        )

    @app.get("/api/transactions")
    @_login_required
    def transactions_api():
        rows = database.fetch_transactions(g.user["id"], app.config["DATABASE"])
        return jsonify([budget.serialize_transaction(row) for row in rows])

    @app.delete("/api/transactions/<int:transaction_id>")
    @_login_required
    def delete_transaction_api(transaction_id):
        if not database.delete_transaction(
            transaction_id, g.user["id"], app.config["DATABASE"]
        ):
            return jsonify({"error": "Transaction not found."}), 404
        return jsonify({"message": "Transaction deleted successfully."})

    @app.get("/api/summary/categories")
    @_login_required
    def category_summary_api():
        return jsonify(budget.get_category_summary(g.user["id"], app.config["DATABASE"]))

    @app.get("/api/reports/monthly")
    @_login_required
    def monthly_reports_api():
        return jsonify(
            budget.get_monthly_summary(g.user["id"], app.config["DATABASE"], months=12)
        )

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found."}), 404
        return error

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
