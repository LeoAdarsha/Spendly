import os
import sys
from datetime import datetime

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    CATEGORIES,
    create_expense,
    create_user,
    get_category_totals,
    get_db,
    get_expense_by_id,
    get_expenses_by_user,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
    update_expense,
)

CATEGORY_TONE = {
    "Food": "accent",
    "Transport": "neutral",
    "Bills": "accent",
    "Health": "accent",
    "Entertainment": "amber",
    "Shopping": "neutral",
    "Other": "neutral",
}

RECENT_LIMIT = 5


def format_currency(amount):
    return "₹{:,.2f}".format(amount)


def _parse_ymd(raw):
    """Parse a 'YYYY-MM-DD' string to a datetime, or None if it can't be parsed.

    Shared by format_date() (stored expense dates) and parse_date_arg() (filter
    bounds off the query string): both accept only that one format and must
    tolerate junk without raising.
    """
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def format_date(raw):
    """Render a stored YYYY-MM-DD expense date as 'Apr 08, 2026'.

    Stored dates are written by us, but a hand-edited row shouldn't take the
    whole page down — an unparseable value falls through unchanged.
    """
    if not raw:
        return ""
    parsed = _parse_ymd(raw)
    return parsed.strftime("%b %d, %Y") if parsed else raw


def parse_date_arg(raw):
    """Normalise a query-string date to 'YYYY-MM-DD', or None if it doesn't parse.

    Filter bounds arrive from typed URLs and stale bookmarks, so an unparseable
    value is ignored rather than raising. Re-formatting also zero-pads a value
    like '2026-9-1' so it compares correctly against the stored dates.
    """
    parsed = _parse_ymd(raw)
    return parsed.strftime("%Y-%m-%d") if parsed else None


def parse_amount(raw):
    """Parse a form-submitted amount to a positive float, or None if invalid.

    Rejects non-numeric input and any value <= 0 so the caller can re-render
    the form with an error rather than storing a bad row.
    """
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def format_month_year(raw):
    """Render a stored created_at timestamp as 'January 2025'.

    SQLite's datetime('now') writes 'YYYY-MM-DD HH:MM:SS', but the column is
    nullable and older rows may carry a bare date.
    """
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%B %Y")
        except (TypeError, ValueError):
            continue
    return ""


def build_initials(name):
    """First letter of the first and last word of a name, uppercased."""
    parts = (name or "").split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# Bootstrap the dev database on startup, but not under pytest — the test suite
# points DB_PATH at a throwaway file and seeds that itself, so importing the app
# must not touch the real expense_tracker.db.
if "pytest" not in sys.modules:
    with app.app_context():
        init_db()
        seed_db()


# ------------------------------------------------------------------ #
# Profile sections                                                    #
#                                                                     #
# The profile view queries once and hands the rows to these three     #
# builders, so each one is a pure transform over sqlite3.Row objects. #
# ------------------------------------------------------------------ #

# --- Section 1: transaction history -- begin ----------------------- #


def build_recent_expenses(expenses):
    """Build the Recent Transactions rows.

    `expenses` — every expense row for the user, already ordered by the SQL
    as date DESC, id DESC. Do not re-sort.

    Returns at most RECENT_LIMIT dicts, newest first, each with:
        id          — the expense row id, for building the edit link
        date        — via format_date()
        description — "" when the column is NULL
        category    — the stored category string
        tone        — CATEGORY_TONE.get(category, "neutral")
        amount      — via format_currency()
    Returns [] for no expenses.
    """
    recent = []
    for row in expenses[:RECENT_LIMIT]:
        category = row["category"]
        recent.append(
            {
                "id": row["id"],
                "date": format_date(row["date"]),
                "description": row["description"] or "",
                "category": category,
                "tone": CATEGORY_TONE.get(category, "neutral"),
                "amount": format_currency(row["amount"]),
            }
        )
    return recent


# --- Section 1: transaction history -- end ------------------------- #


# --- Section 2: summary stats -- begin ----------------------------- #


def build_summary_stats(expenses, category_totals):
    """Build the three summary stat-card values.

    `expenses` — every expense row for the user (not the truncated five).
    `category_totals` — rows of (category, total), ordered total DESC.

    Returns a dict with exactly:
        total_spent       — via format_currency(), summed over ALL expenses
        transaction_count — count of ALL expenses, as an int
        top_category      — highest-total category name, or None when there
                            are none (the template renders an em dash)
    """
    total_spent = sum(expense["amount"] for expense in expenses)
    return {
        "total_spent": format_currency(total_spent),
        "transaction_count": len(expenses),
        "top_category": category_totals[0]["category"] if category_totals else None,
    }


# --- Section 2: summary stats -- end ------------------------------- #


# --- Section 3: category breakdown -- begin ------------------------ #


def build_category_breakdown(category_totals):
    """Build the Spending by Category progress rows.

    `category_totals` — rows of (category, total), already ordered total
    DESC by the SQL. Do not re-sort.

    Returns one dict per category, in that order, each with:
        category     — the category name
        amount       — via format_currency()
        percent      — int share of the HIGHEST total, so the first row is
                       always 100
        percent_step — percent rounded to the nearest multiple of 5 and
                       clamped to 0..100; static/css/profile.css only
                       defines .category-bar-fill--0 .. --100 in 5% steps
                       and inline styles are forbidden
    Guard against a zero/absent maximum. Returns [] for no totals.
    """
    if not category_totals:
        return []

    highest = category_totals[0]["total"] or 0

    breakdown = []
    for row in category_totals:
        total = row["total"] or 0
        percent = round(total / highest * 100) if highest > 0 else 0
        percent = max(0, min(100, int(percent)))
        breakdown.append(
            {
                "category": row["category"],
                "amount": format_currency(total),
                "percent": percent,
                "percent_step": int(round(percent / 5.0)) * 5,
            }
        )
    return breakdown


# --- Section 3: category breakdown -- end -------------------------- #


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #


@app.context_processor
def inject_current_user():
    # Runs for every render, error pages included — it must never raise.
    user_id = session.get("user_id")
    if user_id is None:
        return {"current_user_name": None}

    user = get_user_by_id(user_id)
    return {"current_user_name": user["name"] if user is not None else None}


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id") is not None:
        return redirect(url_for("landing"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password.strip():
            return (
                render_template("register.html", error="All fields are required."),
                400,
            )

        if get_user_by_email(email) is not None:
            return (
                render_template("register.html", error="Email already registered."),
                400,
            )

        password_hash = generate_password_hash(password)
        user_id = create_user(name, email, password_hash)
        session["user_id"] = user_id
        return redirect(url_for("landing"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id") is not None:
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user_by_email(email)

        if user is None or not check_password_hash(user["password_hash"], password):
            return (
                render_template("login.html", error="Invalid email or password."),
                401,
            )

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    user = get_user_by_id(session["user_id"])
    if user is None:
        # Session points at a row that no longer exists — e.g. the database
        # file was recreated underneath a live session.
        session.clear()
        return redirect(url_for("login"))

    start = parse_date_arg(request.args.get("start"))
    end = parse_date_arg(request.args.get("end"))

    expenses = get_expenses_by_user(user["id"], start, end)
    category_totals = get_category_totals(user["id"], start, end)

    stats = build_summary_stats(expenses, category_totals)

    return render_template(
        "profile.html",
        name=user["name"],
        email=user["email"],
        member_since=format_month_year(user["created_at"]),
        initials=build_initials(user["name"]),
        recent_expenses=build_recent_expenses(expenses),
        categories=build_category_breakdown(category_totals),
        start_value=start or "",
        end_value=end or "",
        filter_active=bool(start or end),
        **stats,
    )


@app.route("/analytics")
def analytics():
    # Same session guard as /profile — a logged-out visitor who types the URL
    # is bounced to the login page rather than seeing the placeholder.
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    today = datetime.now().strftime("%Y-%m-%d")

    if request.method == "POST":
        amount_raw = request.form.get("amount", "")
        category = request.form.get("category", "")
        date_raw = request.form.get("date", "")
        description = request.form.get("description", "").strip()

        amount = parse_amount(amount_raw)
        date = parse_date_arg(date_raw)

        error = None
        if amount is None:
            error = "Enter an amount greater than zero."
        elif category not in CATEGORIES:
            error = "Choose a category from the list."
        elif date is None:
            error = "Enter a valid date."
        elif len(description) > 200:
            error = "Keep the description under 200 characters."

        if error is not None:
            return (
                render_template(
                    "add_expense.html",
                    categories=CATEGORIES,
                    error=error,
                    amount_value=amount_raw,
                    category_value=category,
                    date_value=date or today,
                    description_value=description,
                ),
                400,
            )

        # The expense always belongs to the logged-in user — never a user_id
        # smuggled in through the form.
        create_expense(session["user_id"], amount, category, date, description or None)
        return redirect(url_for("profile"))

    return render_template(
        "add_expense.html",
        categories=CATEGORIES,
        amount_value="",
        category_value="",
        date_value=today,
        description_value="",
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    # Ownership is enforced in the query — another user's id (or a missing one)
    # comes back as None and is treated as "not found".
    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    if request.method == "POST":
        amount_raw = request.form.get("amount", "")
        category = request.form.get("category", "")
        date_raw = request.form.get("date", "")
        description = request.form.get("description", "").strip()

        amount = parse_amount(amount_raw)
        date = parse_date_arg(date_raw)

        error = None
        if amount is None:
            error = "Enter an amount greater than zero."
        elif category not in CATEGORIES:
            error = "Choose a category from the list."
        elif date is None:
            error = "Enter a valid date."
        elif len(description) > 200:
            error = "Keep the description under 200 characters."

        if error is not None:
            return (
                render_template(
                    "edit_expense.html",
                    expense_id=id,
                    categories=CATEGORIES,
                    error=error,
                    amount_value=amount_raw,
                    category_value=category,
                    date_value=date or expense["date"],
                    description_value=description,
                ),
                400,
            )

        # The target row is pinned by (id, session user) — never a user_id
        # smuggled in through the form.
        update_expense(
            id, session["user_id"], amount, category, date, description or None
        )
        return redirect(url_for("profile"))

    return render_template(
        "edit_expense.html",
        expense_id=id,
        categories=CATEGORIES,
        amount_value=expense["amount"],
        category_value=expense["category"],
        date_value=expense["date"],
        description_value=expense["description"] or "",
    )


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
