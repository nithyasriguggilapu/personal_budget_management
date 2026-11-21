import json
import tempfile
import unittest
from pathlib import Path

from app import create_app


class BudgetAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "test-budget.db")
        self.app = create_app({"TESTING": True, "DATABASE": database_path})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_income_expense_summary_and_restart_persistence(self):
        income = self.client.post(
            "/api/income",
            json={"amount": "25000.50", "source": "Part-time work", "date": "2026-11-20"},
        )
        self.assertEqual(income.status_code, 201)
        expense = self.client.post(
            "/api/expenses",
            json={
                "amount": "1250.25",
                "category": "Food",
                "description": "Groceries",
                "date": "2026-11-21",
            },
        )
        self.assertEqual(expense.status_code, 201)
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["summary"]["total_income"], 25000.5)
        self.assertEqual(dashboard["summary"]["total_expenses"], 1250.25)
        self.assertEqual(dashboard["summary"]["balance"], 23750.25)
        self.assertEqual(dashboard["summary"]["transaction_count"], 2)

        restarted_client = create_app(
            {"TESTING": True, "DATABASE": self.app.config["DATABASE"]}
        ).test_client()
        self.assertEqual(len(restarted_client.get("/api/transactions").get_json()), 2)

    def test_invalid_transactions_are_rejected_without_storage(self):
        response = self.client.post(
            "/api/income",
            data=json.dumps({"amount": "-5", "source": "Allowance", "date": "2026-11-21"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Amount must be greater than zero", response.get_json()["error"])
        self.assertEqual(self.client.get("/api/transactions").get_json(), [])

    def test_category_validation_and_delete(self):
        invalid = self.client.post(
            "/api/expenses",
            json={
                "amount": 5,
                "category": "Invalid",
                "description": "Test",
                "date": "2026-11-21",
            },
        )
        self.assertEqual(invalid.status_code, 400)
        created = self.client.post(
            "/api/expenses",
            json={
                "amount": 5,
                "category": "Education",
                "description": "Notebook",
                "date": "2026-11-21",
            },
        )
        transaction_id = created.get_json()["transaction"]["id"]
        self.assertEqual(self.client.delete(f"/api/transactions/{transaction_id}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/transactions/{transaction_id}").status_code, 404)

    def test_pages_render_and_monthly_report_has_twelve_months(self):
        for path in ("/", "/transactions", "/reports", "/settings"):
            self.assertEqual(self.client.get(path).status_code, 200)
        report = self.client.get("/api/reports/monthly").get_json()
        self.assertEqual(len(report), 12)


if __name__ == "__main__":
    unittest.main()
