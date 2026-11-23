import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


PASSWORD = "SecurePass123!"


def csrf_token(client, path="/login"):
    response = client.get(path)
    match = re.search(
        r'<meta name="csrf-token" content="([^"]+)"', response.get_data(as_text=True)
    )
    if not match:
        raise AssertionError("CSRF token was not rendered")
    return match.group(1)


def register_user(client, full_name="Test User", email="test@example.com",
                  username="testuser", password=PASSWORD, confirm_password=None):
    token = csrf_token(client, "/register")
    return client.post(
        "/register",
        data={
            "csrf_token": token,
            "full_name": full_name,
            "email": email,
            "username": username,
            "password": password,
            "confirm_password": (
                password if confirm_password is None else confirm_password
            ),
        },
    )


def login_user(client, identifier="testuser", password=PASSWORD):
    token = csrf_token(client)
    return client.post(
        "/login",
        data={
            "csrf_token": token,
            "identifier": identifier,
            "password": password,
        },
    )


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "test-budget.db")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": self.database_path,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def api_headers(self, client=None):
        return {
            "X-CSRFToken": csrf_token(client or self.client, "/"),
        }

    def create_and_login(self, client=None, **details):
        client = client or self.client
        response = register_user(client, **details)
        self.assertEqual(response.status_code, 302)
        response = login_user(
            client,
            identifier=details.get("username", "testuser"),
            password=details.get("password", PASSWORD),
        )
        self.assertEqual(response.status_code, 302)


class AuthenticationTests(AppTestCase):
    def test_registration_hashes_password_and_login_accepts_email_or_username(self):
        response = register_user(self.client)
        self.assertEqual(response.status_code, 302)

        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT email, username, password_hash FROM users"
            ).fetchone()
        self.assertEqual(row[:2], ("test@example.com", "testuser"))
        self.assertNotEqual(row[2], PASSWORD)

        login = login_user(self.client, identifier="test@example.com")
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.headers["Location"], "/")
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_duplicate_email_and_username_and_password_validation(self):
        self.assertEqual(register_user(self.client).status_code, 302)

        duplicate_email = register_user(
            self.client, email="TEST@example.com", username="anotheruser"
        )
        self.assertEqual(duplicate_email.status_code, 400)
        self.assertIn("already registered", duplicate_email.get_data(as_text=True))

        duplicate_username = register_user(
            self.client, email="another@example.com", username="TESTUSER"
        )
        self.assertEqual(duplicate_username.status_code, 400)
        self.assertIn("already registered", duplicate_username.get_data(as_text=True))

        mismatch = register_user(
            self.client, email="mismatch@example.com", username="mismatch",
            confirm_password="DifferentPass123!",
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("do not match", mismatch.get_data(as_text=True))

        weak_password = register_user(
            self.client, email="weak@example.com", username="weakuser",
            password="password",
        )
        self.assertEqual(weak_password.status_code, 400)
        self.assertIn("12–128 characters", weak_password.get_data(as_text=True))

        invalid_email = register_user(
            self.client, email="not-an-email", username="invalidemail"
        )
        self.assertEqual(invalid_email.status_code, 400)
        self.assertIn("valid email", invalid_email.get_data(as_text=True))

    def test_bad_credentials_logout_and_protected_routes(self):
        for path in ("/", "/transactions", "/reports", "/settings"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)

        register_user(self.client)
        bad_login = login_user(self.client, password="WrongPassword123!")
        self.assertEqual(bad_login.status_code, 401)
        self.assertIn("incorrect", bad_login.get_data(as_text=True))

        self.assertEqual(login_user(self.client).status_code, 302)
        logout = self.client.post(
            "/logout", data={"csrf_token": csrf_token(self.client, "/")}
        )
        self.assertEqual(logout.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/login").status_code, 200)

    def test_csrf_is_required_for_auth_and_budget_changes(self):
        self.assertEqual(
            self.client.post(
                "/register",
                data={
                    "full_name": "Test User",
                    "email": "test@example.com",
                    "username": "testuser",
                    "password": PASSWORD,
                    "confirm_password": PASSWORD,
                },
            ).status_code,
            400,
        )
        self.create_and_login()
        response = self.client.post(
            "/api/income",
            json={"amount": "10", "source": "Work", "date": "2026-11-20"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("could not be verified", response.get_json()["error"])

    def test_unsafe_next_redirects_are_ignored(self):
        register_user(self.client)
        for unsafe_target in ("https://example.com/", r"/\\example.com"):
            response = self.client.post(
                "/login",
                data={
                    "csrf_token": csrf_token(self.client),
                    "identifier": "testuser",
                    "password": PASSWORD,
                    "next": unsafe_target,
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], "/")
            self.client.post(
                "/logout", data={"csrf_token": csrf_token(self.client, "/")}
            )


class BudgetAppTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.create_and_login()

    def test_income_expense_summary_and_restart_persistence(self):
        income = self.client.post(
            "/api/income",
            json={
                "amount": "25000.50",
                "source": "Part-time work",
                "date": "2026-11-20",
            },
            headers=self.api_headers(),
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
            headers=self.api_headers(),
        )
        self.assertEqual(expense.status_code, 201)
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["summary"]["total_income"], 25000.5)
        self.assertEqual(dashboard["summary"]["total_expenses"], 1250.25)
        self.assertEqual(dashboard["summary"]["balance"], 23750.25)
        self.assertEqual(dashboard["summary"]["transaction_count"], 2)

        restarted_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": self.database_path,
            }
        )
        restarted_client = restarted_app.test_client()
        login_user(restarted_client)
        self.assertEqual(
            len(restarted_client.get("/api/transactions").get_json()), 2
        )

    def test_invalid_transactions_are_rejected_without_storage(self):
        response = self.client.post(
            "/api/income",
            json={"amount": "-5", "source": "Allowance", "date": "2026-11-21"},
            headers=self.api_headers(),
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
            headers=self.api_headers(),
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
            headers=self.api_headers(),
        )
        transaction_id = created.get_json()["transaction"]["id"]
        headers = self.api_headers()
        self.assertEqual(
            self.client.delete(
                f"/api/transactions/{transaction_id}", headers=headers
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/transactions/{transaction_id}", headers=headers
            ).status_code,
            404,
        )

    def test_accounts_cannot_read_or_delete_each_others_transactions(self):
        first = self.client.post(
            "/api/income",
            json={"amount": 100, "source": "Salary", "date": "2026-11-20"},
            headers=self.api_headers(),
        )
        transaction_id = first.get_json()["transaction"]["id"]

        second_client = self.app.test_client()
        self.create_and_login(
            second_client,
            full_name="Second User",
            email="second@example.com",
            username="seconduser",
        )
        self.assertEqual(second_client.get("/api/transactions").get_json(), [])
        self.assertEqual(
            second_client.delete(
                f"/api/transactions/{transaction_id}",
                headers=self.api_headers(second_client),
            ).status_code,
            404,
        )
        self.assertEqual(
            second_client.get("/api/dashboard").get_json()["summary"]["balance"],
            0,
        )

    def test_existing_unowned_transactions_are_preserved_but_not_exposed(self):
        legacy_path = str(Path(self.temp_dir.name) / "legacy-budget.db")
        with closing(sqlite3.connect(legacy_path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        type TEXT NOT NULL,
                        amount_cents INTEGER NOT NULL,
                        category TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        transaction_date TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO transactions
                        (type, amount_cents, category, description, transaction_date)
                    VALUES ('income', 50000, 'Legacy', 'Old record', '2026-11-01')
                    """
                )
        upgraded_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": legacy_path,
            }
        )
        client = upgraded_app.test_client()
        register_user(client)
        login_user(client)
        self.assertEqual(client.get("/api/transactions").get_json(), [])
        self.assertEqual(
            client.get("/api/dashboard").get_json()["summary"]["balance"], 0
        )
        with closing(sqlite3.connect(legacy_path)) as connection:
            legacy = connection.execute(
                "SELECT description, user_id FROM transactions"
            ).fetchone()
        self.assertEqual(legacy, ("Old record", None))

    def test_pages_render_and_monthly_report_has_twelve_months(self):
        for path in ("/", "/transactions", "/reports", "/settings"):
            self.assertEqual(self.client.get(path).status_code, 200)
        report = self.client.get("/api/reports/monthly").get_json()
        self.assertEqual(len(report), 12)


if __name__ == "__main__":
    unittest.main()
