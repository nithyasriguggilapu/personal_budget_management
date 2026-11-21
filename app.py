"""Flask entry point for the Personal Budget Management System."""

from pathlib import Path

from flask import Flask, jsonify, render_template, request

import budget
import database


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=str(Path(__file__).resolve().parent / "instance" / "budget.db")
    )
    if test_config:
        app.config.update(test_config)
    database.init_db(app.config["DATABASE"])

    @app.get("/")
    def dashboard():
        return render_template("index.html", categories=budget.EXPENSE_CATEGORIES)

    @app.get("/transactions")
    def transactions_page():
        return render_template("transactions.html")

    @app.get("/reports")
    def reports_page():
        return render_template("reports.html")

    @app.get("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.get("/api/dashboard")
    def dashboard_api():
        path = app.config["DATABASE"]
        rows = database.fetch_transactions(path, limit=8)
        return jsonify(
            {
                "summary": budget.get_summary(path),
                "recent_transactions": [
                    budget.serialize_transaction(row) for row in rows
                ],
                "categories": budget.get_category_summary(path),
                "monthly": budget.get_monthly_summary(path),
            }
        )

    @app.post("/api/income")
    def add_income_api():
        try:
            transaction = budget.add_income(
                request.get_json(silent=True), app.config["DATABASE"]
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
    def add_expense_api():
        try:
            transaction = budget.add_expense(
                request.get_json(silent=True), app.config["DATABASE"]
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
    def transactions_api():
        rows = database.fetch_transactions(app.config["DATABASE"])
        return jsonify([budget.serialize_transaction(row) for row in rows])

    @app.delete("/api/transactions/<int:transaction_id>")
    def delete_transaction_api(transaction_id):
        if not database.delete_transaction(transaction_id, app.config["DATABASE"]):
            return jsonify({"error": "Transaction not found."}), 404
        return jsonify({"message": "Transaction deleted successfully."})

    @app.get("/api/summary/categories")
    def category_summary_api():
        return jsonify(budget.get_category_summary(app.config["DATABASE"]))

    @app.get("/api/reports/monthly")
    def monthly_reports_api():
        return jsonify(budget.get_monthly_summary(app.config["DATABASE"], months=12))

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found."}), 404
        return error

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
