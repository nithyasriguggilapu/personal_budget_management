# Pennywise — Personal Budget Management System

A responsive budget dashboard built with Flask, SQLite, HTML, CSS, JavaScript, and Chart.js. Create a private account, record income and expenses, review your balance and transaction history, and explore spending by category and month. Currency is displayed in Indian Rupees (INR).

## Requirements

- Python 3.9 or newer
- `pip`
- An internet connection to load the Google Fonts and Chart.js CDN assets (the application itself and its data run locally)
- A secret `SECRET_KEY` environment variable for stable, secure sessions in deployment

## Setup and run

Open the `personal_budget_management` folder in VS Code. In the integrated PowerShell terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

If PowerShell prevents environment activation, run this once in that terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Open [http://127.0.0.1:5000/](http://127.0.0.1:5000/) in your browser. Stop the local server with **Ctrl+C** in the terminal. The SQLite database is initialized automatically at `instance/budget.db` the first time the app runs.

On local development runs without a configured `SECRET_KEY`, the app generates a temporary random key. This is suitable only for local testing; sessions will be invalidated when the app restarts.

## Accounts and deployment

- Register at `/register`, then log in at `/login`. Authenticated users are redirected to the budget dashboard.
- Every dashboard, report, transaction, settings, and budget API route requires a login. API writes also require the CSRF token supplied by the page.
- Passwords are hashed with Werkzeug. Session cookies are HTTP-only and use `SameSite=Lax`.
- Before deploying, configure a long, random `SECRET_KEY` in the process environment. When HTTPS is enabled at Nginx, also set `SESSION_COOKIE_SECURE=true`. Do not commit the key to source control.
- Password reset email is not configured; the “Forgot password?” page directs users to the site administrator.

Initialization adds the `users` table and a nullable `transactions.user_id` column/index. Existing transactions are preserved with no owner and are deliberately hidden from every account; they are not automatically assigned. If pre-existing records should belong to a user, review and assign them explicitly as a separate, backed-up data migration.

## Features

- Add income with amount, source, and date; add expenses with amount, category, description, and date.
- Validate required fields, positive amounts, supported expense categories, and dates.
- Automatically calculate total income, total expenses, remaining balance, and transaction count.
- Browse, search, and filter transaction history; delete a transaction after confirming.
- View expense totals by category in a doughnut chart and detailed report.
- Compare income and expenses across the last 6 or 12 months.
- Save transactions in SQLite so they remain available after restarting.
- Register and log in with unique email addresses and usernames; budget records are isolated by user.
- Responsive navigation and dashboard for desktop, tablet, and mobile.

## Project structure

```text
personal_budget_management/
├── app.py                 # Flask app factory, authentication, pages, and JSON API
├── budget.py              # Transaction validation and budget calculations
├── database.py            # SQLite schema and persistence helpers
├── requirements.txt       # Python dependencies
├── README.md
├── instance/
│   └── budget.db          # Created automatically at runtime
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── transactions.html
│   ├── reports.html
│   └── settings.html
│   ├── auth_base.html
│   ├── login.html
│   ├── register.html
│   └── forgot_password.html
├── static/
│   ├── css/style.css      # Budget and responsive authentication styles
│   └── js/
│       ├── script.js
│       └── auth.js
└── tests/
    └── test_app.py        # Focused API and persistence tests
```

## API routes

- `GET /api/dashboard` — summary, recent transactions, categories, and six-month chart data
- `POST /api/income` — create an income transaction
- `POST /api/expenses` — create an expense transaction
- `GET /api/transactions` — return transaction history
- `DELETE /api/transactions/<id>` — delete a transaction
- `GET /api/summary/categories` — expense totals by category
- `GET /api/reports/monthly` — monthly income and expense totals for the last 12 months

Authentication routes: `GET/POST /register`, `GET/POST /login`, and `POST /logout`. Protected API requests without a session receive `401`. Send the CSRF token in the `X-CSRFToken` header for JSON `POST` and `DELETE` requests.

The add endpoints accept JSON. Income uses `amount`, `source`, and `date`; expenses use `amount`, `category`, `description`, and `date`.

## Run tests

```powershell
python -m unittest discover -s tests -v
```

## Existing console program

The original `Budge_app.py` is left untouched in this folder. The web application preserves its core calculations (income, expenses, remaining balance, and category summaries) and adds durable storage and a browser UI.
